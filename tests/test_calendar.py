from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from fund_signal import calendar as calendar_module
from fund_signal.calendar import ChinaTradingCalendar


def test_uses_akshare_trading_days_and_writes_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(
        calendar_module,
        "_fetch_akshare_trading_days",
        lambda: {"2026-10-09"},
    )
    config = {"source": "akshare", "cache_ttl_days": 30}
    trading_calendar = ChinaTradingCalendar(config, tmp_path)

    assert trading_calendar.should_run_today(date(2026, 10, 9)) is True
    assert trading_calendar.should_run_today(date(2026, 10, 1)) is False
    assert (tmp_path / "china_trading_days.json").exists()


def test_uses_stale_cache_when_akshare_fails(tmp_path, monkeypatch):
    _write_cache(tmp_path / "china_trading_days.json", ["2026-10-09"], days_ago=60)

    def fail():
        raise RuntimeError("network down")

    monkeypatch.setattr(calendar_module, "_fetch_akshare_trading_days", fail)
    config = {"source": "akshare", "cache_ttl_days": 30}

    assert ChinaTradingCalendar(config, tmp_path).should_run_today(date(2026, 10, 9)) is True


def test_falls_back_to_manual_and_weekday_when_no_calendar_available(tmp_path, monkeypatch):
    def fail():
        raise RuntimeError("network down")

    monkeypatch.setattr(calendar_module, "_fetch_akshare_trading_days", fail)
    config = {
        "source": "akshare",
        "manual_holidays": ["2026-06-01"],
        "manual_workdays": ["2026-05-31"],
    }
    trading_calendar = ChinaTradingCalendar(config, tmp_path)

    assert trading_calendar.should_run_today(date(2026, 5, 31)) is True
    assert trading_calendar.should_run_today(date(2026, 6, 1)) is False
    assert trading_calendar.should_run_today(date(2026, 6, 2)) is True
    assert trading_calendar.should_run_today(date(2026, 6, 6)) is False


def _write_cache(path, trading_days: list[str], days_ago: int):
    payload = {
        "fetched_at": (datetime.now() - timedelta(days=days_ago)).isoformat(timespec="seconds"),
        "trading_days": trading_days,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
