import json
import time
import uuid
import datetime as dt
from typing import Dict, Any, Optional

import streamlit as st

from intake.auth import require_access
from intake.kb import load_kb, route_intent, KBResult
from intake.deadlines import load_deadline_rules, compute_deadlines, parse_date
from intake.llm import LLMClient, LLMConfig, AUTO_FILE_THRESHOLD
from intake.packet import build_packet_text, build_packet_filename, as_download_bytes, URGENT_INTENTS
from intake.emailer import send_packet_email, EmailConfig


APP_TITLE = "AI Intake Steward — Teamsters Local 795"
APP_SUBTITLE = "Report an issue 24/7. Your steward will be notified automatically."


def init_state():
    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())
    if "started_at" not in st.session_state:
        st.session_state.started_at = time.time()
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "intake" not in st.session_state:
        session_ref = str(uuid.uuid4())[:8].upper()
        st.session_state.intake = {
            "member_email": "",
            "case_title": "",
            "facts": [],
            "questions_asked": 0,
            "session_ref": session_ref,
            "routing": {"intent": "", "kb_hits": []},
        }
    if "packet_ready" not in st.session_state:
        st.session_state.packet_ready = False
    if "packet_text" not in st.session_state:
        st.session_state.packet_text = ""
    if "report_filed" not in st.session_state:
        st.session_state.report_filed = False
    if "llm_config" not in st.session_state:
        st.session_state.llm_config = {}


def ui_header():
    st.title(APP_TITLE)
    st.caption(APP_SUBTITLE)
    st.divider()


def ui_sidebar(config: Dict[str, Any], deadline_rules: Dict[str, Any]):
    with st.sidebar:
        st.header("Your Report")

        st.session_state.intake["member_email"] = st.text_input(
            "Your email (required)",
            value=st.session_state.intake.get("member_email", ""),
            placeholder="name@example.com",
            key="member_email_input",
        ).strip()

        st.session_state.intake["case_title"] = st.text_input(
            "Brief title (optional)",
            value=st.session_state.intake.get("case_title", ""),
            placeholder="e.g. 'Late call-in warning'",
            key="case_title_input",
        ).strip()

        # File Now button — available after the member has given at least 2 responses
        # (Turn 0 confirms the issue type; Turn 1 adds at least one detail or clarification)
        questions = st.session_state.intake.get("questions_asked", 0)
        if questions >= 2 and not st.session_state.report_filed:
            st.divider()
            to_addr = config["email"].get("to_email", "") if config["email"].get("enabled") else ""
            if to_addr:
                st.caption(f"Ready to submit? Report will be sent to **{to_addr}**.")
            else:
                st.caption("Ready to submit? Download the packet and forward to your steward.")
            if st.button("File Report Now", type="primary", use_container_width=True):
                st.session_state["file_now_requested"] = True

        # Confirmation display
        if st.session_state.report_filed:
            ref = st.session_state.intake.get("session_ref", "")
            to_addr = config["email"].get("to_email", "") if config["email"].get("enabled") else ""
            st.divider()
            if to_addr:
                st.success(f"Report filed.\nSent to: {to_addr}\nReference: **{ref}**")
            else:
                st.success(f"Report filed.\nReference: **{ref}**")

        # --- Deadline Calculator (always visible) ---
        st.divider()
        st.subheader("Deadline Calculator")
        st.caption("Art. 10 — workdays only (Sat/Sun/holidays excluded)")

        _stored_date = parse_date(st.session_state.intake.get("incident_date", ""))
        incident_date = st.date_input(
            "Incident / notification date",
            value=_stored_date or dt.date.today(),
            max_value=dt.date.today(),
            key="incident_date_picker",
        )
        # Persist the chosen date so the packet can use it
        st.session_state.intake["incident_date"] = incident_date.isoformat()

        steps = compute_deadlines(incident_date, deadline_rules)
        today = dt.date.today()
        for name, due, _note in steps:
            # Short label: strip the citation "(Art. X Sec. Y)" and anything after "—"
            short = name.split("—")[-1].split("(")[0].strip() if "—" in name else name.split("(")[0].strip()
            due_fmt = due.strftime("%b %-d, %Y")
            delta = (due - today).days
            if delta < 0:
                status = f":red[OVERDUE by {abs(delta)}d]"
            elif delta <= 5:
                status = f":orange[{delta}d left — act soon]"
            else:
                status = f"{delta}d"
            st.markdown(f"**{due_fmt}** · {short} · {status}")

        if st.session_state.get("is_admin", False):
            with st.expander("Advanced"):
                allowed_models = config["llm"]["allowed_models"]
                default_model = config["llm"]["default_model"]
                model = st.selectbox(
                    "Model",
                    options=allowed_models,
                    index=allowed_models.index(default_model),
                )
                temperature = st.slider(
                    "Temperature",
                    min_value=0.0, max_value=1.0,
                    value=float(config["llm"]["temperature"]),
                    step=0.05,
                )
                st.session_state["llm_config"] = {"model": model, "temperature": temperature}

            with st.expander("Packet"):
                if st.button("Build Packet (manual)"):
                    st.session_state.packet_ready = True

        st.divider()
        if st.button("Reset Session"):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()


def add_message(role: str, content: str):
    st.session_state.messages.append({
        "role": role,
        "content": content,
        "ts": dt.datetime.now().isoformat(timespec="seconds"),
    })


def render_chat():
    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])


def system_banner():
    st.info(
        "Facts only · no legal determinations · steward review required before any action.",
        icon="🛡️",
    )


def ensure_required_email():
    # Skip the gate once the report is filed — email was already captured at that point.
    if st.session_state.get("report_filed"):
        return
    email = st.session_state.intake.get("member_email", "").strip()
    if not email or "@" not in email:
        st.warning("Enter your email in the sidebar to continue.")
        st.stop()


def do_file_report(
    intake: Dict[str, Any],
    kb: Dict[str, Any],
    deadline_rules: Dict[str, Any],
    email_config: Dict[str, Any],
) -> Optional[str]:
    """Build packet, attempt email if configured, mark report filed. Returns error str or None."""
    # Re-route on the full conversation so the packet reflects all turns, not just the last one.
    facts = intake.get("facts", [])
    if facts:
        full_result = route_intent(" ".join(facts), kb)
        intake["routing"]["intent"] = full_result.intent
        intake["routing"]["kb_hits"] = [h.__dict__ for h in full_result.hits]

    packet_text = build_packet_text(intake=intake, kb=kb, deadline_rules=deadline_rules)
    st.session_state.packet_text = packet_text
    st.session_state.packet_ready = True
    st.session_state.report_filed = True

    if email_config.get("enabled"):
        intent = intake.get("routing", {}).get("intent", "general")
        urgent = intent in URGENT_INTENTS
        ref = intake.get("session_ref", "")
        member = intake.get("member_email", "unknown")
        flag = "URGENT" if urgent else "REPORT"
        subject = f"[{flag}] AI Intake — {intent.upper()} — {member} — Ref {ref}"

        cfg = EmailConfig(
            provider=email_config["provider"],
            sendgrid_api_key=email_config["sendgrid_api_key"],
            from_email=email_config["from_email"],
            to_email=email_config["to_email"],
        )
        ok, err = send_packet_email(cfg=cfg, subject=subject, body_text=packet_text)
        if not ok:
            return err

    return None


def main():
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    init_state()

    config = {
        "auth": {
            "enabled": True,
            "admin_email": st.secrets.get("ADMIN_EMAIL", "").strip(),
            "admin_code": st.secrets.get("ADMIN_PASSCODE", "").strip(),
            "passcodes": st.secrets.get("PASSCODES_JSON", "[]"),
        },
        "llm": {
            "api_key": st.secrets.get("OPENAI_API_KEY", ""),
            "allowed_models": json.loads(st.secrets.get("ALLOWED_MODELS_JSON", '["gpt-4.1-mini","gpt-4.1"]')),
            "default_model": st.secrets.get("DEFAULT_MODEL", "gpt-4.1"),
            "temperature": float(st.secrets.get("TEMPERATURE", 0.2)),
            "max_output_tokens": int(st.secrets.get("MAX_OUTPUT_TOKENS", 1400)),
            "hard_token_budget": int(st.secrets.get("HARD_TOKEN_BUDGET", 40000)),
        },
        "email": {
            "enabled": bool(st.secrets.get("EMAIL_ENABLED", False)),
            "provider": st.secrets.get("EMAIL_PROVIDER", "sendgrid"),
            "sendgrid_api_key": st.secrets.get("SENDGRID_API_KEY", ""),
            "from_email": st.secrets.get("FROM_EMAIL", ""),
            "to_email": st.secrets.get("TO_EMAIL", ""),
        },
        "deadlines": {"rules_path": "deadlines.json"},
        "kb": {"path": "kb.json"},
    }

    require_access(config["auth"])

    kb = load_kb(config["kb"]["path"])
    deadline_rules = load_deadline_rules(config["deadlines"]["rules_path"])

    ui_header()
    system_banner()
    ui_sidebar(config, deadline_rules)
    ensure_required_email()

    llm_cfg = LLMConfig(
        api_key=config["llm"]["api_key"],
        model=st.session_state["llm_config"].get("model", config["llm"]["default_model"]),
        temperature=float(st.session_state["llm_config"].get("temperature", config["llm"]["temperature"])),
        max_output_tokens=config["llm"]["max_output_tokens"],
        hard_token_budget=config["llm"]["hard_token_budget"],
    )
    llm = LLMClient(llm_cfg)

    render_chat()

    # Handle "File Report Now" button click (sidebar)
    if st.session_state.pop("file_now_requested", False) and not st.session_state.report_filed:
        try:
            err = do_file_report(
                intake=st.session_state.intake,
                kb=kb,
                deadline_rules=deadline_rules,
                email_config=config["email"],
            )
        except Exception as exc:
            st.error(f"Filing failed unexpectedly: {exc}. Your information was not lost — try again.")
            err = None
        else:
            ref = st.session_state.intake.get("session_ref", "")
            add_message(
                "assistant",
                f"Your report has been filed. Your steward will review this and be in touch. "
                f"Save any written notices or documents you've received.\n\n**Reference: {ref}**",
            )
            if err:
                st.warning(f"Report saved, but email notification failed: {err}")
            st.rerun()

    # Filed confirmation banner
    if st.session_state.report_filed:
        ref = st.session_state.intake.get("session_ref", "")
        intent = st.session_state.intake.get("routing", {}).get("intent", "")
        to_addr = config["email"].get("to_email", "") if config["email"].get("enabled") else ""
        sent_note = f" Sent to **{to_addr}**." if to_addr else ""
        if intent in URGENT_INTENTS:
            st.error(f"Report filed — **URGENT** case flagged for immediate steward attention.{sent_note} Reference: **{ref}**")
        else:
            st.success(f"Report filed and steward notified.{sent_note} Reference: **{ref}**")

    # Chat input
    placeholder = (
        "Add anything else for your steward (optional)."
        if st.session_state.report_filed
        else "Describe what happened."
    )
    user_msg = st.chat_input(placeholder)

    if user_msg:
        add_message("user", user_msg)

        # Route against the full conversation so later messages don't lose context
        # established in earlier turns (e.g. "flat tire" alone won't drop the
        # attendance article that "late to work" correctly matched on Turn 0).
        prior_facts = st.session_state.intake.get("facts", [])
        route_text = " ".join(prior_facts + [user_msg])
        kb_result: KBResult = route_intent(route_text, kb)
        st.session_state.intake["routing"]["intent"] = kb_result.intent
        st.session_state.intake["routing"]["kb_hits"] = [h.__dict__ for h in kb_result.hits]

        # Determine if this turn should wrap up and trigger auto-filing
        questions_after = st.session_state.intake["questions_asked"] + 1
        is_final = questions_after >= AUTO_FILE_THRESHOLD and not st.session_state.report_filed

        assistant_text = llm.intake_turn(
            user_msg=user_msg,
            intake_state=st.session_state.intake,
            kb_result=kb_result,
            deadline_rules=deadline_rules,
            final=is_final,
        )

        add_message("assistant", assistant_text)
        st.session_state.intake["facts"].append(user_msg)
        st.session_state.intake["questions_asked"] += 1

        # Auto-file after the final intake turn
        if is_final:
            try:
                err = do_file_report(
                    intake=st.session_state.intake,
                    kb=kb,
                    deadline_rules=deadline_rules,
                    email_config=config["email"],
                )
            except Exception as exc:
                st.error(f"Auto-filing failed unexpectedly: {exc}. Use 'File Report Now' to retry.")
            else:
                if err:
                    st.warning(f"Report saved, but email notification failed: {err}")

        st.rerun()

    # Packet display (shown after filing or manual build)
    if st.session_state.packet_ready and st.session_state.packet_text:
        st.divider()
        st.subheader("Steward Review Packet")

        col1, col2 = st.columns([3, 1])
        with col1:
            st.text_area("Packet (copyable)", st.session_state.packet_text, height=360)
        with col2:
            filename = build_packet_filename(st.session_state.intake)
            st.download_button(
                "Download (.txt)",
                data=as_download_bytes(st.session_state.packet_text),
                file_name=filename,
                mime="text/plain",
                use_container_width=True,
            )
            if not config["email"]["enabled"]:
                st.info("Email not configured.\nDownload and forward to your steward.")
            elif not st.session_state.report_filed:
                # Manual email send (fallback if auto-send failed)
                to_addr = config["email"].get("to_email", "")
                if to_addr:
                    st.caption(f"Sends to: {to_addr}")
                if st.button("Email to Steward", use_container_width=True):
                    err = do_file_report(
                        intake=st.session_state.intake,
                        kb=kb,
                        deadline_rules=deadline_rules,
                        email_config=config["email"],
                    )
                    if err:
                        st.error(f"Email failed: {err}")
                    else:
                        st.success("Sent.")
                    st.rerun()


if __name__ == "__main__":
    main()
