import json
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any


def _tokenize(text: str) -> set:
    """Split text into lowercase alphanumeric tokens.
    Prevents short tags like 'ot' from matching inside longer words like 'not' or 'got'."""
    return set(re.findall(r'[a-z0-9]+', text.lower()))


@dataclass
class KBHit:
    id: str
    title: str
    intent: str
    tags: List[str]
    answer: str
    contract_articles: List[Dict[str, str]] = field(default_factory=list)


@dataclass
class KBResult:
    intent: str
    hits: List[KBHit]


def load_kb(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def route_intent(user_msg: str, kb: Dict[str, Any]) -> KBResult:
    """
    Deterministic, KB-first routing:
    - simple keyword/tag scoring (no embeddings required)
    - returns top hits for grounding

    Tag matching rules:
    - Single-word tags (no space, no hyphen): token-level match only, so short tags
      like "ot" cannot fire inside words like "not", "got", "another".
    - Multi-word / hyphenated tags: substring match (phrases are specific enough).
    Secondary hits are filtered to >= 40% of the top score to prevent low-confidence
    items from contaminating the packet with irrelevant contract articles.
    """
    msg = user_msg.lower()
    msg_tokens = _tokenize(msg)
    items = kb.get("items", [])
    scored = []

    for it in items:
        tags = [t.lower() for t in it.get("tags", [])]
        keywords = [k.lower() for k in it.get("keywords", [])]
        score = 0
        for t in tags:
            if ' ' not in t and '-' not in t:
                # single-word tag: must match as a whole token
                if t in msg_tokens:
                    score += 3
            else:
                # multi-word / hyphenated tag: substring is fine
                if t in msg:
                    score += 3
        for k in keywords:
            if k in msg:
                score += 2
        # small bonus for direct intent label mention (token-level to avoid "pay" in "display")
        intent_label = (it.get("intent") or "").lower()
        if intent_label and intent_label in msg_tokens:
            score += 1
        if score > 0:
            scored.append((score, it))

    scored.sort(key=lambda x: x[0], reverse=True)

    top_score = scored[0][0] if scored else 1
    hits = []
    for score, it in scored[:3]:
        # Always include the top hit; secondary hits must reach >= 40% of top score
        if not hits or score >= max(2, top_score * 0.4):
            hits.append(KBHit(
                id=it.get("id", ""),
                title=it.get("title", ""),
                intent=it.get("intent", "general"),
                tags=it.get("tags", []),
                answer=it.get("answer", ""),
                contract_articles=it.get("contract_articles", []),
            ))

    intent = hits[0].intent if hits else "general"
    return KBResult(intent=intent, hits=hits)
