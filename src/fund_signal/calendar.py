from __future__ import annotations

from datetime import date


def should_run_today(today: date, calendars: dict) -> bool:
    text = today.isoformat()
    if text in calendars.get("manual_workdays", []):
        return True
    if text in calendars.get("manual_holidays", []):
        return False
    return today.weekday() < 5
