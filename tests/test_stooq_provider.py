from __future__ import annotations

from datetime import date

from fund_signal.providers.stooq_provider import StooqProvider, _normalize_symbol


def test_normalize_symbols_for_configured_overseas_assets():
    assert _normalize_symbol("QQQ") == "qqq.us"
    assert _normalize_symbol("SPY") == "spy.us"
    assert _normalize_symbol("1321.T") == "1321.jp"


def test_history_parses_csv_and_filters_dates(monkeypatch):
    requested_params = {}
    monkeypatch.setenv("STOOQ_API_KEY", "test-key")

    class Response:
        text = (
            "Date,Open,High,Low,Close,Volume\n"
            "2026-05-29,450,455,449,454,1000\n"
            "2026-06-01,454,456,453,455,1200\n"
        )

        def raise_for_status(self):
            return None

    def fake_get(url, params, headers, timeout):
        requested_params.update(params)
        return Response()

    monkeypatch.setattr("fund_signal.providers.stooq_provider.requests.get", fake_get)

    bars = StooqProvider().history("QQQ", start=date(2026, 6, 1))

    assert requested_params["s"] == "qqq.us"
    assert requested_params["i"] == "d"
    assert requested_params["apikey"] == "test-key"
    assert len(bars) == 1
    assert bars[0].date == date(2026, 6, 1)
    assert bars[0].close == 455
    assert bars[0].source == "stooq"


def test_history_requires_api_key(monkeypatch):
    monkeypatch.delenv("STOOQ_API_KEY", raising=False)

    try:
        StooqProvider().history("QQQ")
    except RuntimeError as exc:
        assert "STOOQ_API_KEY" in str(exc)
    else:
        raise AssertionError("Expected missing STOOQ_API_KEY error")
