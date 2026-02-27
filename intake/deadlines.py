import json
import datetime as dt
from typing import Dict, Any, Optional


def load_deadline_rules(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_date(s: str) -> Optional[dt.date]:
    try:
        return dt.datetime.strptime(s.strip(), "%Y-%m-%d").date()
    except Exception:
        return None


def compute_deadlines(event_date: dt.date, rules: Dict[str, Any]) -> Dict[str, str]:
    """
    Simple rule engine: adds N calendar days.
    You can extend later to business-day logic.
    """
    out = {}
    for rule in rules.get("rules", []):
        name = rule["name"]
        days = int(rule["days"])
        due = event_date + dt.timedelta(days=days)
        out[name] = due.isoformat()
    return out
