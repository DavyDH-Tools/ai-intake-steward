import datetime as dt
from typing import Dict, Any, List, Tuple

from intake.deadlines import compute_deadlines, parse_date


# These intents trigger urgent flagging in the email subject and packet header
URGENT_INTENTS = {"discipline", "suspension", "harassment", "drug_test"}


# ---------------------------------------------------------------------------
# Per-intent question banks
# Each entry: (question_text, [signal_words])
# If ANY signal appears in the combined facts text, the question is considered
# answered and is omitted from Section 3.
# ---------------------------------------------------------------------------

_Q = List[Tuple[str, List[str]]]

_DATE_SIGNALS = [
    "january", "february", "march", "april", "may", "june", "july",
    "august", "september", "october", "november", "december",
    "jan ", "feb ", "mar ", "apr ", "jun ", "jul ", "aug ", "sep ", "oct ", "nov ", "dec ",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "yesterday", "today", "last week", "this week",
    "/202", "/20",          # date separators like 3/14/2025
    " am ", " pm ", "a.m.", "p.m.", "o'clock", ":00", ":30", ":15", ":45",
    "morning", "afternoon", "evening",
]

_VERBATIM_SIGNALS = [
    '"', "\u201c", "\u201d",  # curly quotes
    "said", "told me", "stated", "he said", "she said", "they said",
    "she told", "he told", "they told", "wrote", "the letter says",
    "the notice says", "words were",
]

_WRITTEN_NOTICE_SIGNALS = [
    "letter", "notice", "write-up", "write up", "written",
    "reprimand", "form", "document", "paperwork", "signed",
    "suspension letter", "termination letter", "investigation notice",
    "no notice", "nothing in writing", "verbal only",
]

_PRIOR_DISCIPLINE_SIGNALS = [
    "first offense", "never been", "no prior", "prior discipline",
    "previous discipline", "before this", "clean record", "first time",
    "no history", "never disciplined", "prior warning", "prior suspension",
    "step 1", "step 2", "step one", "step two",
]

_WITNESS_SIGNALS = [
    "witness", "no one else", "alone", "nobody else", "no witnesses",
    "saw it", "were there", "was present", "coworker", "driver ",
    "operator ", "bystander", "passengers",
]

_STEWARD_SIGNALS = [
    "steward", "union rep", "no steward", "without a steward",
    "alone", "by myself", "no union", "waived", "waiver",
]

QUESTION_SETS: Dict[str, _Q] = {
    "discipline": [
        ("Exact date and time of the incident / meeting", _DATE_SIGNALS),
        ("Exact words used by management (verbatim if possible)", _VERBATIM_SIGNALS),
        ("Written notice received (reprimand, investigation notice)", _WRITTEN_NOTICE_SIGNALS),
        ("Prior discipline in the same series (rolling 12-month window)", _PRIOR_DISCIPLINE_SIGNALS),
        ("Names of any witnesses present", _WITNESS_SIGNALS),
        ("Whether a steward or union rep was present at the meeting", _STEWARD_SIGNALS),
    ],
    "suspension": [
        ("Exact date of suspension / termination notice", _DATE_SIGNALS),
        (
            "Length of suspension (number of days, paid or unpaid)",
            ["day suspension", "days suspension", "unpaid", "days off",
             "one day", "two day", "three day", "week suspension",
             "terminated", "fired", "discharged", "discharge"],
        ),
        ("Written suspension / termination letter received and retained", _WRITTEN_NOTICE_SIGNALS),
        ("Prior discipline in the same series (rolling 12-month window)", _PRIOR_DISCIPLINE_SIGNALS),
        ("Whether a steward was present at any pre-disciplinary meeting", _STEWARD_SIGNALS),
    ],
    "drug_test": [
        (
            "Date of the test and whether it was random, for-cause, or post-accident",
            _DATE_SIGNALS + ["random", "for cause", "post-accident", "post accident",
                             "reasonable suspicion"],
        ),
        (
            "Chain of custody followed and collection witnessed",
            ["chain of custody", "witnessed", "sealed", "collector",
             "observed", "collection site", "lab", "specimen"],
        ),
        (
            "Whether member was on duty or off duty at time of test",
            ["on duty", "off duty", "on the clock", "off the clock",
             "working", "not working", "my day off"],
        ),
        (
            "Test result received and whether split-sample re-test was requested",
            ["positive", "negative", "result", "split sample",
             "re-test", "retest", "mro", "medical review officer"],
        ),
        ("Written policy or notice citing grounds for the test", _WRITTEN_NOTICE_SIGNALS),
    ],
    "attendance": [
        (
            "Total number of absences or occurrences cited by management",
            ["occurrence", "occurrences", "absences", "absent",
             "times i", "incidents", "how many", "count of",
             "number of times"],
        ),
        (
            "Whether FMLA, ADA, or medical documentation was submitted",
            ["fmla", "ada", "doctor", "medical", "documentation",
             "paperwork", "intermittent", "leave", "excuse", "note from"],
        ),
        (
            "Whether progressive attendance steps (verbal → written → suspension) were followed",
            ["verbal", "written warning", "first step", "second step",
             "progressive", "prior warning", "counseling"],
        ),
        (
            "Whether call-out procedure (right number, right time) was followed",
            ["called in", "called out", "called the number", "texted",
             "notification", "let them know", "told my supervisor",
             "left a message"],
        ),
    ],
    "safety": [
        ("Exact date and time of the incident or unsafe condition observed", _DATE_SIGNALS),
        (
            "Whether member reported the safety concern to a supervisor before the incident",
            ["reported", "told my supervisor", "notified", "complained",
             "raised the concern", "mentioned it", "said something",
             "never reported", "didn't report"],
        ),
        (
            "Whether an ARC (Accident Review Committee) review has been scheduled",
            ["arc", "accident review", "review committee", "scheduled",
             "meeting date", "review date", "no arc", "haven't heard"],
        ),
        ("Names of any witnesses or supervisors present at the time", _WITNESS_SIGNALS),
        (
            "Any injury, vehicle damage, or property damage noted in the report",
            ["injur", "hurt", "damage", "damaged", "property",
             "vehicle", "bus", "no injury", "not hurt", "fine",
             "nobody was hurt"],
        ),
    ],
    "harassment": [
        ("Exact date(s) and location(s) of the incident(s)", _DATE_SIGNALS),
        ("Exact words or actions used (verbatim if possible)", _VERBATIM_SIGNALS),
        (
            "Whether this has occurred more than once (establish a pattern)",
            ["again", "multiple times", "pattern", "keeps doing", "keeps saying",
             "happened before", "first time", "only once", "never before"],
        ),
        ("Names of any witnesses present", _WITNESS_SIGNALS),
        (
            "Whether member previously reported this to HR or a supervisor",
            ["reported", "told hr", "told my supervisor", "complaint",
             "human resources", "never reported", "didn't report",
             "filed a complaint"],
        ),
    ],
}

# Generic fallback for unrouted or unrecognised intents
_GENERIC_QUESTIONS: _Q = [
    ("Exact date and time of the incident", _DATE_SIGNALS),
    ("Exact words used by management (verbatim if possible)", _VERBATIM_SIGNALS),
    ("Written notice received", _WRITTEN_NOTICE_SIGNALS),
    ("Names of any witnesses present", _WITNESS_SIGNALS),
]


def _open_questions(intent: str, facts: List[str]) -> List[str]:
    """Return only the questions whose signal words are absent from facts."""
    combined = " ".join(facts).lower()
    question_set = QUESTION_SETS.get(intent, _GENERIC_QUESTIONS)
    return [
        q for q, signals in question_set
        if not any(s.lower() in combined for s in signals)
    ]


# ---------------------------------------------------------------------------

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
    missing = _open_questions(intent, facts)
    if missing:
        lines.append("Confirm or collect the following before filing a grievance:")
        for q in missing:
            lines.append(f"- {q}")
    else:
        lines.append("All standard elements appear to be covered in the member's account above.")
        lines.append("Steward: verify details and confirm nothing material was omitted.")
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
    incident_date = parse_date(intake.get("incident_date", ""))
    if incident_date:
        lines.append(f"Incident / notification date: {incident_date.isoformat()}")
        steps = compute_deadlines(incident_date, deadline_rules)
        for name, due, note in steps:
            lines.append(f"  {name}")
            lines.append(f"    Due: {due.strftime('%A, %B %-d, %Y')}  ({note})")
            lines.append("")
    else:
        lines.append("Incident date not provided — enter date in the sidebar calculator to get exact deadlines.")
        for r in deadline_rules.get("rules", []):
            lines.append(f"  {r.get('name')}: {r.get('days')} workdays")
    lines.append("")

    lines.append("=" * 60)
    lines.append("END PACKET — STEWARD REVIEW REQUIRED BEFORE ANY ACTION")
    lines.append(f"Ref: {session_ref}")
    return "\n".join(lines)


def as_download_bytes(text: str) -> bytes:
    return text.encode("utf-8")
