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
"""

TURN0_TEMPLATE = """A union member just described their situation for the first time. Your ONLY job right now is to name the issue type, cite the relevant contract article, and ask the member to confirm.

Routed intent: {intent}
KB hits (includes contract_articles with exact language from the CBA):
{kb_hits}

Member's message:
{user_msg}

STRICT RULES — YOU MUST FOLLOW THESE EXACTLY:
- DO NOT ask about dates, times, call-in windows, witnesses, documents, or any facts yet.
- DO NOT list or summarize facts you think you heard.
- DO NOT ask an evidence question of any kind.
- ONLY name the issue type, cite the governing contract article, and ask ONE confirmation question.

Output exactly this format and nothing else:
Issue type: [specific label, e.g. "Attendance — Call-In Procedure Violation" or "Discipline — 3-Day Suspension" or "Overtime — Skipped on List"]
Contract: [cite the most relevant article/section from the KB hits and quote the key language, e.g. "Art. 19 Sec. 2 — a 'late' includes failure to notify dispatch 60 minutes in advance of report time."]
[One sentence: "It sounds like this is about [plain-language description]."]
[One short question: "Does that sound right, or is there a different angle you're focused on?"]
"""

TURN_TEMPLATE = """Turn number: {questions_asked}

Context:
- Intake state: {intake_state}
- Routed intent: {intent}
- KB hits (includes contract_articles with exact CBA language): {kb_hits}
- Deadline rules: {deadline_rules}

User message:
{user_msg}

Task:
1) Extract any new concrete facts from the user message (date/time, who, exact words, documents).
2) If the sub-issue is not yet clear, ask ONE question to narrow it further.
3) Once the sub-issue is clear, ask ONE question that increases evidentiary quality.
4) If the issue involves time-sensitive discipline or a meeting, ask for the event date to compute deadlines.

Return format:
Issue type: [specific label — always include]
Contract: [cite the most relevant article/section from KB hits and quote the key language]
Facts:
- [bullet fact extracted from this message]
Framing: [1-2 sentences using "possible misapplication" or "possible noncompliance" — cite specific article, e.g. "possible noncompliance with Art. 19 Sec. 2"]
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

        questions_asked = intake_state.get("questions_asked", 0)

        if questions_asked == 0:
            prompt = TURN0_TEMPLATE.format(
                intent=kb_result.intent,
                kb_hits=json.dumps([h.__dict__ for h in kb_result.hits], ensure_ascii=False),
                user_msg=user_msg,
            )
        else:
            prompt = TURN_TEMPLATE.format(
                questions_asked=questions_asked,
                intake_state=json.dumps(intake_state, ensure_ascii=False),
                intent=kb_result.intent,
                kb_hits=json.dumps([h.__dict__ for h in kb_result.hits], ensure_ascii=False),
                deadline_rules=json.dumps(deadline_rules, ensure_ascii=False),
                user_msg=user_msg,
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
