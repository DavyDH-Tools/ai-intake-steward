import datetime as dt
from typing import Dict, Any, List


# These intents trigger urgent flagging in the email subject and packet header
URGENT_INTENTS = {"suspension", "harassment", "drug_test"}


def build_packet_filename(intake: Dict[str, Any]) -> str:
    base = intake.get("case_title") or "intake_packet"
    safe = "".join([c for c in base if c.isalnum() or c in (" ", "_", "-")]).strip().replace(" ", "_")
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M")
    return f"{safe}_{stamp}.txt"


def build_packet_text(intake: Dict[str, Any], kb: Dict[str, Any], deadline_rules: Dict[str, Any]) -> str:
    routing = intake.get("routing", {})
    kb_hits = routing.get("kb_hits", [])
    intent = routing.get("intent", "")
    session_ref = intake.get("session_ref", "N/A")
    urgent = intent in URGENT_INTENTS

    lines = []
    lines.append("AI INTAKE STEWARD — STEWARD REVIEW PACKET")
    if urgent:
        lines.append("!!! URGENT — REVIEW PROMPTLY !!!")
    lines.append("=" * 60)
    lines.append(f"Generated:    {dt.datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"Reference:    {session_ref}")
    lines.append(f"Member Email: {intake.get('member_email', '(not provided)')}")
    lines.append(f"Case Title:   {intake.get('case_title', '(not set)')}")
    lines.append(f"Intent:       {intent or '(unrouted)'}")
    lines.append("")

    lines.append("1) MEMBER'S ACCOUNT (in order received)")
    lines.append("-" * 60)
    facts = intake.get("facts", [])
    if facts:
        for i, f in enumerate(facts, start=1):
            lines.append(f"{i}. {f}")
    else:
        lines.append("(no facts captured)")
    lines.append("")

    lines.append("2) GOVERNING CONTRACT LANGUAGE")
    lines.append("-" * 60)
    cited = False
    for h in kb_hits:
        articles = h.get("contract_articles", [])
        if articles:
            cited = True
            lines.append(f"[ {h.get('title', '')} ]")
            for art in articles:
                cite = art.get("cite", "")
                text = art.get("text", "")
                if cite.lower() == "note":
                    lines.append(f"  NOTE: {text}")
                else:
                    lines.append(f"  {cite}:")
                    lines.append(f"  \"{text}\"")
                lines.append("")
    if not cited:
        lines.append("(No specific article matched — steward to identify applicable provision.)")
    lines.append("")

    lines.append("3) OPEN QUESTIONS / MISSING ELEMENTS")
    lines.append("-" * 60)
    lines.append("Confirm or collect the following before filing a grievance:")
    lines.append("- Exact date and time of the incident")
    lines.append("- Exact words used by management (verbatim if possible)")
    lines.append("- Written notice received (reprimand, suspension letter, investigation notice)")
    lines.append("- Prior discipline in the same series (rolling 12-month window)")
    lines.append("- Names of any witnesses present")
    lines.append("")

    lines.append("4) EXHIBITS TO REQUEST / PRESERVE")
    lines.append("-" * 60)
    lines.append("- Any written discipline (reprimand, notice of investigation, suspension letter)")
    lines.append("- Attendance/dispatch records, timeclock, radio logs, supervisor notes")
    lines.append("- Relevant contract article pages")
    lines.append("- Video/audio if applicable (bus camera, facility camera)")
    lines.append("")

    lines.append("5) DEADLINE NOTES (Article 10 — workdays, excluding Sat/Sun/holidays)")
    lines.append("-" * 60)
    lines.append("Provide the key event date (YYYY-MM-DD) to compute exact filing deadlines.")
    for r in deadline_rules.get("rules", []):
        lines.append(f"  {r.get('name')}: {r.get('days')} workdays")
    lines.append("")

    lines.append("=" * 60)
    lines.append("END PACKET — STEWARD REVIEW REQUIRED BEFORE ANY ACTION")
    lines.append(f"Ref: {session_ref}")
    return "\n".join(lines)


def as_download_bytes(text: str) -> bytes:
    return text.encode("utf-8")
