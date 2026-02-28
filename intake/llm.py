import json
from dataclasses import dataclass
from typing import Dict, Any

from openai import OpenAI


@dataclass
class LLMConfig:
    api_key: str
    model: str
    temperature: float
    max_output_tokens: int
    hard_token_budget: int


SYSTEM_RULES = """You are the AI Intake Steward.
ROLE: Intake-only assistant for union steward casework.
BOUNDARIES:
- Facts-only. Ask one question at a time.
- Do NOT decide merit or make determinations.
- Use neutral language: "possible misapplication", "possible noncompliance", "possible procedural defect".
- Do NOT invent facts. If missing, ask.
- Output must be clean-room and defensible (timestamps, quotes, documents, witnesses).
- Do not store or request sensitive personal data beyond the minimum required (email + narrative).
ISSUE NARROWING (critical — do this before collecting evidence):
- Step 1: Identify the specific issue type from the KB hits and the member's words (e.g., "Written Warning — Attendance", "3-Day Suspension", "Overtime List Skipped", "Seniority — Bid Violation", "FMLA Leave Denied").
- Step 2: On the very first turn, confirm the issue type with the member before asking for evidence.
- Step 3: Once the issue type is confirmed, narrow to the specific sub-issue (e.g., for discipline: written warning vs. suspension vs. termination; for overtime: mandatory OT vs. OT denied vs. wrong list order).
- Never skip ahead to evidence questions before you know exactly what type of issue you are dealing with.
OUTPUT STYLE:
- Always begin with "Issue type: [specific label]".
- Short, direct.
- One question at the end.
"""

TURN_TEMPLATE = """Turn number: {questions_asked} (0 = member's first message)

Context:
- Intake state: {intake_state}
- Routed intent: {intent}
- KB hits: {kb_hits}
- Deadline rules: {deadline_rules}

User message:
{user_msg}

Task:
TURN 0 (first response):
  - Identify the most likely issue type from the routed intent, KB hits, and the member's words.
  - State the issue type clearly (e.g., "It sounds like this is about a written warning for attendance.").
  - If the intent is "general" or no KB hit scored well, ask the member directly which category fits best and list 2-3 possibilities.
  - Confirm the issue type with ONE short question before collecting any evidence.

TURN 1+ (subsequent responses):
  1) Extract any new concrete facts from the user message (date/time, who, exact words, documents).
  2) If the sub-issue is not yet clear, ask ONE question to narrow it further (e.g., "Was this a written warning, suspension, or termination?" or "Were you skipped on the OT list or forced when you should have been bypassed?").
  3) Once the sub-issue is clear, ask ONE question that increases evidentiary quality.
  4) If the issue involves time-sensitive discipline or a meeting, ask for the event date to compute deadlines.

Return format:
Issue type: [specific label — always include, e.g. "Attendance — Written Warning" or "Overtime — Skipped on List" or "Seniority — Bid Violation"]
Facts:
- [bullet fact, if any extracted]
- [bullet fact, if any extracted]
Framing: [1-2 sentences using "possible misapplication" or "possible noncompliance" — no determinations]
Question: [single question on one line]
"""


class LLMClient:
    def __init__(self, cfg: LLMConfig):
        if not cfg.api_key:
            raise RuntimeError("Missing OPENAI_API_KEY")
        self.cfg = cfg
        self.client = OpenAI(api_key=cfg.api_key)
        self.tokens_used_est = 0

    def _budget_check(self, add_estimate: int = 1200):
        # Very rough guardrail; you can wire real token tracking later.
        if (self.tokens_used_est + add_estimate) > self.cfg.hard_token_budget:
            raise RuntimeError("Session token budget exceeded (hard limit).")

    def intake_turn(self, user_msg: str, intake_state: Dict[str, Any], kb_result, deadline_rules: Dict[str, Any]) -> str:
        self._budget_check()

        prompt = TURN_TEMPLATE.format(
            questions_asked=intake_state.get("questions_asked", 0),
            intake_state=json.dumps(intake_state, ensure_ascii=False),
            intent=kb_result.intent,
            kb_hits=json.dumps([h.__dict__ for h in kb_result.hits], ensure_ascii=False),
            deadline_rules=json.dumps(deadline_rules, ensure_ascii=False),
            user_msg=user_msg
        )

        resp = self.client.responses.create(
            model=self.cfg.model,
            input=[
                {"role": "system", "content": SYSTEM_RULES},
                {"role": "user", "content": prompt},
            ],
            temperature=self.cfg.temperature,
            max_output_tokens=self.cfg.max_output_tokens,
        )

        # Estimate tokens used (rough)
        self.tokens_used_est += 1200

        return resp.output_text.strip()
