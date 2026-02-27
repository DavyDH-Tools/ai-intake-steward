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
OUTPUT STYLE:
- Short, direct.
- One question at the end.
"""

TURN_TEMPLATE = """Context:
- Intake state: {intake_state}
- Routed intent: {intent}
- KB hits: {kb_hits}
- Deadline rules: {deadline_rules}

User message:
{user_msg}

Task:
1) Extract any new concrete facts from the user message (do not restate long).
2) Ask ONE next question that increases evidentiary quality (date/time, who, exact words, documents, discipline type).
3) If the user indicates time-sensitive discipline or a meeting, ask for the date of the event to compute deadlines.

Return format:
- 3-6 bullet facts (if present)
- 1 short paragraph: "possible misapplication" framing (no determinations)
- ONE question (single line starting with "Question:")
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
