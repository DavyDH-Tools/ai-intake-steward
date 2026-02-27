import os
import json
import time
import uuid
import datetime as dt
from typing import Dict, Any, List, Optional, Tuple

import streamlit as st

from intake.auth import require_access
from intake.kb import load_kb, route_intent, KBResult
from intake.deadlines import load_deadline_rules, compute_deadlines
from intake.llm import LLMClient, LLMConfig
from intake.packet import build_packet_text, build_packet_filename, as_download_bytes
from intake.emailer import send_packet_email, EmailConfig


APP_TITLE = "AI Intake Steward — Teamsters Local 795"
APP_SUBTITLE = "Fact-gathering only (no determinations). Steward review required."


def init_state():
    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())
    if "started_at" not in st.session_state:
        st.session_state.started_at = time.time()
    if "messages" not in st.session_state:
        st.session_state.messages = []  # list of {role, content, ts}
    if "intake" not in st.session_state:
        st.session_state.intake = {
            "member_email": "",
            "case_title": "",
            "facts": [],
            "timeline": [],
            "people": [],
            "documents": [],
            "questions_asked": 0,
            "routing": {"intent": "", "kb_hits": []},
        }
    if "packet_ready" not in st.session_state:
        st.session_state.packet_ready = False
    if "packet_text" not in st.session_state:
        st.session_state.packet_text = ""


def ui_header():
    st.title(APP_TITLE)
    st.caption(APP_SUBTITLE)
    st.divider()


def ui_sidebar(config: Dict[str, Any]):
    with st.sidebar:
        st.header("Controls")

        st.session_state.intake["member_email"] = st.text_input(
            "Member email (required)",
            value=st.session_state.intake.get("member_email", ""),
            placeholder="name@example.com",
        ).strip()

        st.session_state.intake["case_title"] = st.text_input(
            "Case title (optional)",
            value=st.session_state.intake.get("case_title", ""),
            placeholder="Short label (ex: 'Late Call-In Reprimand')",
        ).strip()

        st.subheader("Model + Cost Controls")

        allowed_models = config["llm"]["allowed_models"]
        default_model = config["llm"]["default_model"]
        model = st.selectbox("Model", options=allowed_models, index=allowed_models.index(default_model))
        temperature = st.slider("Temperature", min_value=0.0, max_value=1.0, value=float(config["llm"]["temperature"]), step=0.05)

        st.session_state["llm_config"] = {
            "model": model,
            "temperature": temperature,
        }

        st.subheader("Packet")
        st.write("Build a steward-review packet at any time.")
        if st.button("Build Packet Now", type="primary"):
            st.session_state.packet_ready = True

        st.subheader("Reset")
        if st.button("Reset Session"):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()


def add_message(role: str, content: str):
    st.session_state.messages.append({
        "role": role,
        "content": content,
        "ts": dt.datetime.now().isoformat(timespec="seconds")
    })


def render_chat():
    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])


def system_banner():
    st.info(
        "Rules: facts only • no determinations • steward review required • "
        "use 'possible misapplication' language • no long-term records stored here.",
        icon="🛡️"
    )


def ensure_required_email():
    email = st.session_state.intake.get("member_email", "").strip()
    if not email or "@" not in email:
        st.warning("Enter a valid member email in the sidebar to continue.")
        st.stop()


def main():
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    init_state()

    # Load config from secrets (Streamlit) with safe defaults
    config = {
        "auth": {
            "enabled": True,
            "admin_email": st.secrets.get("ADMIN_EMAIL", "").strip(),
            "passcodes": st.secrets.get("PASSCODES_JSON", "[]"),
        },
        "llm": {
            "api_key": st.secrets.get("OPENAI_API_KEY", ""),
            "allowed_models": json.loads(st.secrets.get("ALLOWED_MODELS_JSON", '["gpt-4.1-mini","gpt-4.1"]')),
            "default_model": st.secrets.get("DEFAULT_MODEL", "gpt-4.1-mini"),
            "temperature": float(st.secrets.get("TEMPERATURE", 0.2)),
            "max_output_tokens": int(st.secrets.get("MAX_OUTPUT_TOKENS", 800)),
            "hard_token_budget": int(st.secrets.get("HARD_TOKEN_BUDGET", 12000)),  # per session
        },
        "email": {
            "enabled": bool(st.secrets.get("EMAIL_ENABLED", False)),
            "provider": st.secrets.get("EMAIL_PROVIDER", "sendgrid"),
            "sendgrid_api_key": st.secrets.get("SENDGRID_API_KEY", ""),
            "from_email": st.secrets.get("FROM_EMAIL", ""),
            "to_email": st.secrets.get("TO_EMAIL", ""),
        },
        "deadlines": {
            "rules_path": "deadlines.json"
        },
        "kb": {
            "path": "kb.json"
        }
    }

    # Gate
    require_access(config["auth"])

    ui_header()
    system_banner()
    ui_sidebar(config)

    ensure_required_email()

    # Load KB + deadline rules
    kb = load_kb(config["kb"]["path"])
    deadline_rules = load_deadline_rules(config["deadlines"]["rules_path"])

    # LLM
    llm_cfg = LLMConfig(
        api_key=config["llm"]["api_key"],
        model=st.session_state["llm_config"]["model"],
        temperature=float(st.session_state["llm_config"]["temperature"]),
        max_output_tokens=config["llm"]["max_output_tokens"],
        hard_token_budget=config["llm"]["hard_token_budget"],
    )
    llm = LLMClient(llm_cfg)

    # Chat display
    render_chat()

    user_msg = st.chat_input("Describe what happened (facts only).")
    if user_msg:
        add_message("user", user_msg)

        # Route intent KB-first
        kb_result: KBResult = route_intent(user_msg, kb)
        st.session_state.intake["routing"]["intent"] = kb_result.intent
        st.session_state.intake["routing"]["kb_hits"] = [h.__dict__ for h in kb_result.hits]

        # Ask next best question OR summarize a fact
        assistant_text = llm.intake_turn(
            user_msg=user_msg,
            intake_state=st.session_state.intake,
            kb_result=kb_result,
            deadline_rules=deadline_rules,
        )

        add_message("assistant", assistant_text)

        # Update intake (lightweight, based on structured hints embedded by the model)
        st.session_state.intake["facts"].append(user_msg)
        st.session_state.intake["questions_asked"] += 1

        st.rerun()

    # Packet assembly on demand
    if st.session_state.packet_ready:
        packet_text = build_packet_text(
            intake=st.session_state.intake,
            kb=kb,
            deadline_rules=deadline_rules,
        )
        st.session_state.packet_text = packet_text

        st.subheader("Steward Review Packet")
        st.text_area("Packet (copyable)", packet_text, height=420)

        filename = build_packet_filename(st.session_state.intake)
        st.download_button(
            "Download Packet (.txt)",
            data=as_download_bytes(packet_text),
            file_name=filename,
            mime="text/plain",
        )

        # Optional email-out
        if config["email"]["enabled"]:
            email_cfg = EmailConfig(
                provider=config["email"]["provider"],
                sendgrid_api_key=config["email"]["sendgrid_api_key"],
                from_email=config["email"]["from_email"],
                to_email=config["email"]["to_email"],
            )
            if st.button("Email packet to steward"):
                ok, err = send_packet_email(
                    cfg=email_cfg,
                    subject=f"AI Intake Packet — {st.session_state.intake.get('case_title') or 'New Case'}",
                    body_text=packet_text,
                )
                if ok:
                    st.success("Sent.")
                else:
                    st.error(f"Email failed: {err}")


if __name__ == "__main__":
    main()
