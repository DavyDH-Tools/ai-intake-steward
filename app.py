"""
AI Intake Steward (v1.7.7) — Wichita Transit / Teamsters Local 795

Key guarantees:
- AI is intake-only (no determinations, no violations)
- Uses "possible misapplication" language only
- Steward remains gatekeeper and decision-maker
- Grievance deadline math matches ACTUAL City practice
"""

import streamlit as st
from openai import OpenAI
from datetime import date, datetime, timedelta
from typing import Set

# ------------------------------------------------------------
# PAGE CONFIGURATION
# ------------------------------------------------------------
st.set_page_config(page_title="AI Intake Steward", page_icon="🛡️")

# ------------------------------------------------------------
# SECURITY
# ------------------------------------------------------------
try:
    api_key = st.secrets["OPENAI_API_KEY"]
except Exception:
    st.error("API Key not found in .streamlit/secrets.toml")
    st.stop()

client = OpenAI(api_key=api_key)

# ------------------------------------------------------------
# CONTRACT LOADING
# ------------------------------------------------------------
@st.cache_data
def load_contract() -> str:
    try:
        with open("contract.txt", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""

contract_text = load_contract()

# ------------------------------------------------------------
# HOLIDAY / DEADLINE LOGIC (LOCKED TO CITY PRACTICE)
# ------------------------------------------------------------
# IMPORTANT:
# - Holidays are observed on the ACTUAL calendar date only
# - NO Friday/Monday substitution
# - Day-before/day-after rules affect PAY ONLY, not deadlines
# - Personal days / well days are NOT holidays

def nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> date:
    d = date(year, month, 1)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d + timedelta(weeks=n - 1)

def last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    if month == 12:
        d = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        d = date(year, month + 1, 1) - timedelta(days=1)
    while d.weekday() != weekday:
        d -= timedelta(days=1)
    return d

def wichita_article31_named_holidays(year: int) -> Set[date]:
    thanksgiving = nth_weekday_of_month(year, 11, 3, 4)
    return {
        date(year, 1, 1),                    # New Year's Day
        nth_weekday_of_month(year, 1, 0, 3), # MLK Day
        nth_weekday_of_month(year, 2, 0, 3), # Presidents Day
        last_weekday_of_month(year, 5, 0),   # Memorial Day
        date(year, 6, 19),                   # Juneteenth
        date(year, 7, 4),                    # Independence Day
        nth_weekday_of_month(year, 9, 0, 1), # Labor Day
        date(year, 11, 11),                  # Veterans Day
        thanksgiving,                        # Thanksgiving
        thanksgiving + timedelta(days=1),    # Day after Thanksgiving
        date(year, 12, 25),                  # Christmas Day
    }

def grievance_deadline(incident: date, workdays: int = 10) -> date:
    holidays = (
        wichita_article31_named_holidays(incident.year)
        | wichita_article31_named_holidays(incident.year + 1)
    )
    cur = incident
    added = 0
    while added < workdays:
        cur += timedelta(days=1)
        if cur.weekday() < 5 and cur not in holidays:
            added += 1
    return cur

def last_safe_filing_date(incident: date) -> date:
    """One workday before the grievance deadline."""
    deadline = grievance_deadline(incident)
    cur = deadline
    holidays = (
        wichita_article31_named_holidays(cur.year)
        | wichita_article31_named_holidays(cur.year - 1)
    )
    while True:
        cur -= timedelta(days=1)
        if cur.weekday() < 5 and cur not in holidays:
            return cur

# ------------------------------------------------------------
# SYSTEM PROMPT
# ------------------------------------------------------------
def get_system_prompt(contract: str) -> str:
    contract_block = contract.strip() if contract.strip() else "No contract text provided."
    return f"""
You are an AI Intake Steward for Teamsters Local 795 (Wichita Transit).

PURPOSE:
- Gather facts in plain language.
- Ask ONE question at a time.
- Produce structured, facts-only outputs for a human steward.

NON-NEGOTIABLES:
- Intake only. Do not decide, file, accuse, or diagnose.
- Do not offer legal opinions.
- Never say "articles violated."
- Use "possible misapplication of Article __" only.
- If uncertain, say "Unknown" and ask follow-up questions.

INTERVIEW STYLE:
- Who / What / When / Where / How
- Accept "I don’t know"

WICHITA-SPECIFIC CHECKS (QUESTIONS ONLY):
- Attendance: call-in timing and who was contacted
- Discipline: was a steward requested or present
- Sick leave: length of absence and documentation
- Pay: pay period and expected vs actual pay

CONTRACT CONTEXT:
{contract_block}

OUTPUT DISCIPLINE:
- Neutral language only
- Facts first
- Steward review required
""".strip()

# ------------------------------------------------------------
# SESSION STATE
# ------------------------------------------------------------
OPENER = (
    "I am the Intake Steward. I’ll ask a few questions to get the facts clear, "
    "then I’ll prepare a summary for your human steward.\n\n"
    "To start: what happened?"
)

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": OPENER}]

# ------------------------------------------------------------
# UI
# ------------------------------------------------------------
st.title("🛡️ AI Intake Steward")

with st.sidebar:
    st.header("Steward Tools")

    if not contract_text.strip():
        st.warning("contract.txt not found. Responses will be general.")

    st.subheader("Grievance Deadline (Article 10)")
    incident_date = st.date_input("Incident Date:", value=datetime.now().date())
    deadline = grievance_deadline(incident_date)
    safe_date = last_safe_filing_date(incident_date)

    st.error(f"Filing Deadline: {deadline.strftime('%A, %b %d, %Y')}")
    st.warning(f"Last Safe Filing Day: {safe_date.strftime('%A, %b %d, %Y')}")

    st.caption(
        "Counts 10 workdays AFTER the incident date. "
        "Excludes weekends and named Article 31 holidays only "
        "(no observed shifts; personal/well days excluded)."
    )

    st.divider()

    if st.button("Reset Conversation"):
        st.session_state.messages = [{"role": "assistant", "content": OPENER}]
        st.rerun()

    st.caption("No permanent storage. Closing this tab clears the session.")

# ------------------------------------------------------------
# CHAT
# ------------------------------------------------------------
for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

if prompt := st.chat_input("Describe the issue..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    api_msgs = [{"role": "system", "content": get_system_prompt(contract_text)}] + st.session_state.messages

    res = client.chat.completions.create(
        model="gpt-4o",
        messages=api_msgs,
        temperature=0.4
    )

    ai_msg = res.choices[0].message.content
    st.session_state.messages.append({"role": "assistant", "content": ai_msg})
    with st.chat_message("assistant"):
        st.markdown(ai_msg)

# ------------------------------------------------------------
# OUTPUTS
# ------------------------------------------------------------
st.divider()
col1, col2 = st.columns(2)

STRICT_SUMMARY_INSTRUCTION = """
Produce a STEWARD INTAKE SUMMARY using EXACT headings:

STEWARD INTAKE SUMMARY
MEMBER NAME:
JOB TITLE / CLASSIFICATION:
INCIDENT DATE(S):
INCIDENT TIME(S):
LOCATION / ASSIGNMENT:
PEOPLE INVOLVED:

FACTS (WHO / WHAT / WHEN / WHERE / HOW):
- Bullet points only

MEMBER CONCERN (IN THEIR WORDS):

TIME-SENSITIVE:
- Yes / No / Unknown (why)

POSSIBLE CONTRACT ISSUE TO REVIEW:
- Use "possible misapplication of Article __" only or "General"

MISSING INFORMATION / FOLLOW-UP QUESTIONS:
- Bullet list
""".strip()

DRAFT_NARRATIVE_INSTRUCTION = """
Draft a STEP 1 GRIEVANCE NARRATIVE.

NON-NEGOTIABLES:
- DRAFT FOR STEWARD REVIEW ONLY
- Do NOT state violations
- Use "possible misapplication" language only
- Facts only, neutral tone

Format EXACTLY:

DRAFT FOR STEWARD REVIEW — STEWARD MUST VERIFY FACTS AND CONTRACT CITATIONS

TO: [Immediate Supervisor — Unknown if not stated]
FROM: Teamsters Local 795
DATE: [Today]
RE: Step 1 Grievance — [Member Name / Unknown]

STATEMENT OF GRIEVANCE:
[1–2 short paragraphs using “Member states...” / “Union contends...”]

POSSIBLE CONTRACT ISSUE TO REVIEW:
- Possible misapplication of Article __ and all other relevant articles

REMEDY REQUESTED:
The Union requests the member be made whole in every way, including but not limited to:
- restoration of pay and benefits if applicable,
- correction or removal of adverse records,
- and any other appropriate relief.

FOLLOW-UP ITEMS FOR STEWARD:
- Bullet list
""".strip()

with col1:
    if st.button("📝 Create Summary"):
        msgs = [{"role": "system", "content": get_system_prompt(contract_text)}]
        msgs.extend(st.session_state.messages)
        msgs.append({"role": "user", "content": STRICT_SUMMARY_INSTRUCTION})

        summary = client.chat.completions.create(
            model="gpt-4o",
            messages=msgs,
            temperature=0.2
        ).choices[0].message.content

        st.text_area("Intake Summary", summary, height=320)
        st.download_button("⬇️ Download Summary", summary, "intake_summary.txt")

with col2:
    if st.button("⚖️ Draft Step 1 Narrative"):
        msgs = [{"role": "system", "content": get_system_prompt(contract_text)}]
        msgs.extend(st.session_state.messages)
        msgs.append({"role": "user", "content": DRAFT_NARRATIVE_INSTRUCTION})

        narrative = client.chat.completions.create(
            model="gpt-4o",
            messages=msgs,
            temperature=0.2
        ).choices[0].message.content

        st.text_area("Step 1 Narrative Draft", narrative, height=320)
        st.download_button("⬇️ Download Narrative", narrative, "grievance_draft.txt")
