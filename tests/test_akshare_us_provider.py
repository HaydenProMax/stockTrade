from __future__ import annotations

from datetime import date

import pandas as pd

from fund_signal.providers.akshare_provider import AkshareProvider


def test_history_uses_akshare_us_daily_for_us_ticker(monkeypatch):
    calls = []

    class FakeAkshare:
        def stock_us_daily(self, symbol, adjust):
            calls.append((symbol, adjust))
            return pd.DataFrame(
                [
                    {
                        "date": pd.Timestamp("2026-05-29"),
                        "open": 737.84,
                        "high": 741.63,
                        "low": 735.25,
                        "close": 738.31,
                        "volume": 37541612,
                    },
                    {
                        "date": pd.Timestamp("2026-06-01"),
                        "open": 737.04,
                        "high": 745.65,
                        "low": 735.99,
                        "close": 742.74,
                        "volume": 33890537,
                    },
                ]
            )

    monkeypatch.setitem(__import__("sys").modules, "akshare", FakeAkshare())

    bars = AkshareProvider().history("QQQ", start=date(2026, 6, 1))

    assert calls == [("QQQ", "")]
    assert len(bars) == 1
    assert bars[0].date == date(2026, 6, 1)
    assert bars[0].close == 742.74
    assert bars[0].source == "akshare:stock_us_daily"


def test_history_uses_sina_global_index_for_nikkei_alias(monkeypatch):
    calls = []

    class FakeAkshare:
        def index_global_hist_sina(self, symbol):
            calls.append(symbol)
            return pd.DataFrame(
                [
                    {
                        "date": pd.Timestamp("2026-06-02"),
                        "open": 66629.60,
                        "high": 66748.06,
                        "low": 65551.13,
                        "close": 66734.24,
                        "volume": 0,
                    }
                ]
            )

    monkeypatch.setitem(__import__("sys").modules, "akshare", FakeAkshare())

    bars = AkshareProvider().history("NIKKEI225")

    assert calls == ["日经225指数"]
    assert len(bars) == 1
    assert bars[0].date == date(2026, 6, 2)
    assert bars[0].close == 66734.24
    assert bars[0].source == "akshare:index_global_hist_sina"
