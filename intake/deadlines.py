import json
import datetime as dt
from typing import Dict, Any, List, Optional, Tuple


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> dt.date:
    """Return the nth weekday (0=Mon..6=Sun) of a given month/year. n=-1 means last."""
    if n > 0:
        first = dt.date(year, month, 1)
        offset = (weekday - first.weekday()) % 7
        return first + dt.timedelta(days=offset + 7 * (n - 1))
    # last occurrence
    if month == 12:
        last = dt.date(year + 1, 1, 1) - dt.timedelta(days=1)
    else:
        last = dt.date(year, month + 1, 1) - dt.timedelta(days=1)
    offset = (last.weekday() - weekday) % 7
    return last - dt.timedelta(days=offset)


def art31_holidays(year: int) -> set:
    """
    Return observed dates of all Art. 31 contract holidays for a given year.
    Saturday holidays shift to Friday; Sunday holidays shift to Monday.
    Personal days are excluded (individual, not fixed dates).
    """
    holidays: set = set()

    def add(d: dt.date) -> None:
        if d.weekday() == 5:        # Saturday -> Friday
            holidays.add(d - dt.timedelta(days=1))
        elif d.weekday() == 6:      # Sunday -> Monday
            holidays.add(d + dt.timedelta(days=1))
        else:
            holidays.add(d)

    add(dt.date(year, 1, 1))                              # New Year's Day
    add(_nth_weekday(year, 1, 0, 3))                      # MLK Jr. Day (3rd Mon Jan)
    add(_nth_weekday(year, 2, 0, 3))                      # Presidents' Day (3rd Mon Feb)
    add(_nth_weekday(year, 5, 0, -1))                     # Memorial Day (last Mon May)
    add(dt.date(year, 6, 19))                             # Juneteenth
    add(dt.date(year, 7, 4))                              # Independence Day
    add(_nth_weekday(year, 9, 0, 1))                      # Labor Day (1st Mon Sep)
    add(dt.date(year, 11, 11))                            # Veterans Day
    thanksgiving = _nth_weekday(year, 11, 3, 4)          # Thanksgiving (4th Thu Nov)
    holidays.add(thanksgiving)
    holidays.add(thanksgiving + dt.timedelta(days=1))     # Day after Thanksgiving
    add(dt.date(year, 12, 25))                            # Christmas Day

    return holidays


def workday_advance(start: dt.date, workdays: int) -> dt.date:
    """Advance N workdays from start, skipping weekends and Art. 31 holidays."""
    holidays = (
        art31_holidays(start.year)
        | art31_holidays(start.year + 1)
        | art31_holidays(start.year + 2)
    )
    current = start
    remaining = workdays
    while remaining > 0:
        current += dt.timedelta(days=1)
        if current.weekday() < 5 and current not in holidays:
            remaining -= 1
    return current


def load_deadline_rules(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_date(s: str) -> Optional[dt.date]:
    try:
        return dt.datetime.strptime(s.strip(), "%Y-%m-%d").date()
    except Exception:
        return None


def compute_deadlines(
    event_date: dt.date,
    rules: Dict[str, Any],
) -> List[Tuple[str, dt.date, str]]:
    """
    Cascade deadlines using Art. 31 workdays (Art. 10 Sec. 5 — Sat/Sun/holidays excluded).
    Each step starts from the previous step's deadline date.
    Returns list of (step_name, due_date, note).
    """
    result = []
    current = event_date
    for rule in rules.get("rules", []):
        name = rule["name"]
        days = int(rule["days"])
        note = rule.get("note", "")
        due = workday_advance(current, days)
        result.append((name, due, note))
        current = due
    return result
