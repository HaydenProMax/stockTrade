from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path


@dataclass
class ChinaTradingCalendar:
    config: dict
    cache_dir: Path | None = None

    def should_run_today(self, today: date) -> bool:
        text = today.isoformat()
        if text in self.config.get("manual_workdays", []):
            return True
        if text in self.config.get("manual_holidays", []):
            return False

        trading_days = self._load_trading_days()
        if trading_days is not None:
            return text in trading_days

        return _weekday_fallback(today)

    def trading_day_lag(self, latest_data_date: date, today: date) -> int:
        lag = 0
        current = latest_data_date + timedelta(days=1)
        while current <= today:
            if self.should_run_today(current):
                lag += 1
            current += timedelta(days=1)
        return lag

    def is_in_last_trading_days(self, today: date, window_days: int) -> bool:
        if not self.should_run_today(today):
            return False
        return 1 <= self.trading_days_until_month_end(today) <= window_days

    def is_last_trading_day(self, today: date) -> bool:
        return self.should_run_today(today) and self.trading_days_until_month_end(today) == 1

    def trading_days_until_month_end(self, today: date) -> int:
        count = 0
        current = today
        while current.month == today.month:
            if self.should_run_today(current):
                count += 1
            current += timedelta(days=1)
        return count

    def _load_trading_days(self) -> set[str] | None:
        if self.config.get("source", "akshare") != "akshare":
            return None
        cache_path = self._cache_path()
        cache_ttl_days = int(self.config.get("cache_ttl_days", 30))

        cached = _read_cache(cache_path, cache_ttl_days)
        if cached is not None:
            return cached

        try:
            trading_days = _fetch_akshare_trading_days()
        except Exception:  # noqa: BLE001 - calendar lookup must degrade gracefully
            stale = _read_cache(cache_path, None)
            if stale is not None:
                return stale
            return None

        _write_cache(cache_path, trading_days)
        return trading_days

    def _cache_path(self) -> Path | None:
        if self.cache_dir is None:
            return None
        path = self.config.get("cache_file", "china_trading_days.json")
        return self.cache_dir / path


def should_run_today(today: date, calendars: dict, cache_dir: Path | None = None) -> bool:
    return ChinaTradingCalendar(calendars, cache_dir).should_run_today(today)


def trading_day_lag(
    latest_data_date: date,
    today: date,
    calendars: dict,
    cache_dir: Path | None = None,
) -> int:
    return ChinaTradingCalendar(calendars, cache_dir).trading_day_lag(latest_data_date, today)


def is_in_last_trading_days(
    today: date,
    calendars: dict,
    window_days: int,
    cache_dir: Path | None = None,
) -> bool:
    return ChinaTradingCalendar(calendars, cache_dir).is_in_last_trading_days(today, window_days)


def is_last_trading_day(today: date, calendars: dict, cache_dir: Path | None = None) -> bool:
    return ChinaTradingCalendar(calendars, cache_dir).is_last_trading_day(today)


def trading_days_until_month_end(
    today: date,
    calendars: dict,
    cache_dir: Path | None = None,
) -> int:
    return ChinaTradingCalendar(calendars, cache_dir).trading_days_until_month_end(today)


def _fetch_akshare_trading_days() -> set[str]:
    import akshare as ak

    data = ak.tool_trade_date_hist_sina()
    if data is None or data.empty:
        raise RuntimeError("AKShare returned empty China trading calendar")
    return {
        _date_text(row["trade_date"])
        for _, row in data.iterrows()
        if row.get("trade_date") is not None
    }


def _read_cache(path: Path | None, ttl_days: int | None) -> set[str] | None:
    if path is None or not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        fetched_at = datetime.fromisoformat(payload["fetched_at"])
        if ttl_days is not None and datetime.now() - fetched_at > timedelta(days=ttl_days):
            return None
        days = payload.get("trading_days", [])
        return set(str(day) for day in days)
    except Exception:  # noqa: BLE001 - bad cache should not block fallback
        return None


def _write_cache(path: Path | None, trading_days: set[str]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "trading_days": sorted(trading_days),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _date_text(value) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return date.fromisoformat(str(value)).isoformat()


def _weekday_fallback(today: date) -> bool:
    return today.weekday() < 5
