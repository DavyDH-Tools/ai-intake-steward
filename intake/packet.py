import datetime as dt
from typing import Dict, Any


def build_packet_filename(intake: Dict[str, Any]) -> str:
    base = intake.get("case_title") or "intake_packet"
    safe = "".join([c for c in base if c.isalnum() or c in (" ", "_", "-")]).strip().replace(" ", "_")
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M")
    return f"{safe}_{stamp}.txt"


def build_packet_text(intake: Dict[str, Any], kb: Dict[str, Any], deadline_rules: Dict[str, Any]) -> str:
    routing = intake.get("routing", {})
    kb_hits = routing.get("kb_hits", [])

    lines = []
    lines.append("AI INTAKE STEWARD — STEWARD REVIEW PACKET")
    lines.append("=" * 60)
    lines.append(f"Generated: {dt.datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"Member Email: {intake.get('member_email','')}")
    lines.append(f"Case Title: {intake.get('case_title','')}")
    lines.append("")

    lines.append("1) RECORD (USER-PROVIDED FACTS)")
    lines.append("-" * 60)
    for i, f in enumerate(intake.get("facts", []), start=1):
        lines.append(f"{i}. {f}")
    lines.append("")

    lines.append("2) ROUTING (KB-FIRST)")
    lines.append("-" * 60)
    lines.append(f"Intent: {routing.get('intent','')}")
    if kb_hits:
        lines.append("KB hits used:")
        for h in kb_hits:
            lines.append(f"- {h.get('title','')}  [intent: {h.get('intent','')}]  [tags: {', '.join(h.get('tags',[]))}]")
    else:
        lines.append("KB hits used: (none)")
    lines.append("")

    lines.append("3) OPEN QUESTIONS / MISSING ELEMENTS")
    lines.append("-" * 60)
    lines.append("UNFILLED: exact date/time, exact management words, documentary proof (notice, reprimand, email), witnesses.")
    lines.append("")

    lines.append("4) EXHIBITS TO REQUEST / PRESERVE")
    lines.append("-" * 60)
    lines.append("- Any written discipline (reprimand, notice of investigation, suspension letter)")
    lines.append("- Attendance/dispatch records, timeclock, radio logs, supervisor notes")
    lines.append("- Relevant policy pages / contract article pages")
    lines.append("- Video/audio if applicable (bus, facility, body cam if any)")
    lines.append("")

    lines.append("5) DEADLINE NOTES")
    lines.append("-" * 60)
    lines.append("Deadline calculation requires the key event date in YYYY-MM-DD format.")
    lines.append("Rules loaded:")
    for r in deadline_rules.get("rules", []):
        lines.append(f"- {r.get('name')} = {r.get('days')} days")
    lines.append("")

    lines.append("END PACKET")
    return "\n".join(lines)


def as_download_bytes(text: str) -> bytes:
    return text.encode("utf-8")
