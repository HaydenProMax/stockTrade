from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from fund_signal.config import AppConfig
from fund_signal.runner import run
from fund_signal.types import PriceBar


def test_dry_run_does_not_persist_records(tmp_path, monkeypatch):
    monkeypatch.setattr("fund_signal.runner.MarketData", _FakeMarketData)
    config = _config(tmp_path)

    message = run(config, mode="afternoon", dry_run=True)

    assert "演练模式" in message
    with sqlite3.connect(tmp_path / "data" / "fund_signal.sqlite") as connection:
        assert connection.execute("select count(*) from runs").fetchone()[0] == 0
        assert connection.execute("select count(*) from signals").fetchone()[0] == 0
        assert connection.execute("select count(*) from allocations").fetchone()[0] == 0


def test_manual_run_persists_assumed_execution(tmp_path, monkeypatch):
    monkeypatch.setattr("fund_signal.runner.MarketData", _FakeMarketData)
    config = _config(tmp_path)

    run(config, mode="manual")

    with sqlite3.connect(tmp_path / "data" / "fund_signal.sqlite") as connection:
        assert connection.execute("select count(*) from runs").fetchone()[0] == 1
        assert connection.execute("select count(*) from signals").fetchone()[0] == 1
        row = connection.execute(
            "select fund_code, amount, executed_amount, status from allocations"
        ).fetchone()
    assert row == ("TEST01", 10, 10, "assumed_executed+purchase_status_unknown")


def test_us_weekly_only_observes_configured_assets(tmp_path, monkeypatch):
    monkeypatch.setattr("fund_signal.runner.MarketData", _FakeMarketData)
    monkeypatch.setattr("fund_signal.runner.date", _SaturdayDate)
    config = _config(tmp_path)
    config.assets["asset_groups"]["other_asset"] = {
        "name": "其他资产",
        "volatility_class": "low",
        "index_symbol": "OTHER",
        "provider": "fake",
        "funds": [],
    }
    config.calendars["us_weekly"] = {
        "weekday": 5,
        "asset_groups": ["test_asset"],
    }

    message = run(config, mode="us_weekly")

    assert "美股周收盘观察" in message
    assert "测试资产" in message
    assert "其他资产" not in message
    with sqlite3.connect(tmp_path / "data" / "fund_signal.sqlite") as connection:
        row = connection.execute(
            "select fund_code, amount, executed_amount, status from allocations"
        ).fetchone()
    assert row == ("ASSET_GROUP", 0, None, "observe_only")


class _FakeMarketData:
    def __init__(self, cache_dir):
        self.cache_dir = cache_dir

    def history(self, symbol, provider_name, start=None, end=None, fallback=("csv",), retries=3):
        first_day = date(2025, 1, 1)
        return [
            PriceBar(
                date=first_day + timedelta(days=index),
                open=100 + index,
                high=100 + index,
                low=100 + index,
                close=100 + index,
                volume=None,
                source="fake",
            )
            for index in range(300)
        ]


class _SaturdayDate(date):
    @classmethod
    def today(cls):
        return cls(2026, 6, 6)


def _config(root) -> AppConfig:
    return AppConfig(
        root=root,
        assets={
            "asset_groups": {
                "test_asset": {
                    "name": "测试资产",
                    "volatility_class": "low",
                    "index_symbol": "TEST",
                    "provider": "fake",
                    "funds": [
                        {
                            "code": "TEST01",
                            "name": "测试基金",
                            "enabled": True,
                            "plans": [
                                {
                                    "type": "fixed_daily",
                                    "amount": 10,
                                    "monthly_budget_amount": 260,
                                }
                            ],
                        }
                    ],
                }
            }
        },
        strategy={
            "drawdown_window_days": 250,
            "volatility_classes": {
                "low": {
                    "bands": [
                        {"max_drawdown": -0.05, "units": 0},
                        {"max_drawdown": None, "units": 1},
                    ]
                }
            },
            "trend_filter": {
                "above_ma_60_multiplier": 0,
                "below_ma_60_above_ma_120_multiplier": 0.5,
                "below_ma_120_multiplier": 1,
            },
        },
        budget={"portfolio_monthly_hard_limit_amount": 5500},
        calendars={"manual_holidays": [], "manual_workdays": []},
    )
