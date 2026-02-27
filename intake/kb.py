import json
from dataclasses import dataclass
from typing import List, Dict, Any


@dataclass
class KBHit:
    id: str
    title: str
    intent: str
    tags: List[str]
    answer: str


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
    """
    msg = user_msg.lower()
    items = kb.get("items", [])
    scored = []

    for it in items:
        tags = [t.lower() for t in it.get("tags", [])]
        keywords = [k.lower() for k in it.get("keywords", [])]
        score = 0
        for t in tags:
            if t in msg:
                score += 3
        for k in keywords:
            if k in msg:
                score += 2
        # small bonus for direct intent label mention
        intent = (it.get("intent") or "").lower()
        if intent and intent in msg:
            score += 1
        if score > 0:
            scored.append((score, it))

    scored.sort(key=lambda x: x[0], reverse=True)

    hits = []
    for _, it in scored[:3]:
        hits.append(KBHit(
            id=it.get("id", ""),
            title=it.get("title", ""),
            intent=it.get("intent", "general"),
            tags=it.get("tags", []),
            answer=it.get("answer", ""),
        ))

    intent = hits[0].intent if hits else "general"
    return KBResult(intent=intent, hits=hits)
