from __future__ import annotations

import os
from datetime import date
from typing import Any

import requests

from fund_signal.providers.base import MarketDataProvider
from fund_signal.types import PriceBar


class AlphaVantageProvider(MarketDataProvider):
    name = "alphavantage"
    base_url = "https://www.alphavantage.co/query"

    def history(self, symbol: str, start: date | None = None, end: date | None = None) -> list[PriceBar]:
        api_key = os.getenv("ALPHAVANTAGE_API_KEY")
        if not api_key:
            raise RuntimeError("Missing ALPHAVANTAGE_API_KEY in environment or .env")

        response = requests.get(
            self.base_url,
            params=_params(symbol, api_key),
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        _raise_for_api_error(payload)

        series = _time_series(payload)
        bars: list[PriceBar] = []
        for date_text, values in sorted(series.items()):
            bar_date = date.fromisoformat(date_text)
            if start and bar_date < start:
                continue
            if end and bar_date >= end:
                continue
            bars.append(
                PriceBar(
                    date=bar_date,
                    open=_optional_float(values, "1. open", "open"),
                    high=_optional_float(values, "2. high", "high"),
                    low=_optional_float(values, "3. low", "low"),
                    close=float(_first(values, "4. close", "close")),
                    volume=_optional_float(values, "5. volume", "volume"),
                    source=self.name,
                )
            )
        return bars


def _normalize_symbol(symbol: str) -> str:
    aliases = {
        "^NDX": "NDX",
        "^GSPC": "SPX",
        "^N225": "NIKKEI225",
        "^HSTECH": "HSTECH",
    }
    return aliases.get(symbol, symbol)


def _params(symbol: str, api_key: str) -> dict[str, str]:
    normalized = _normalize_symbol(symbol)
    if symbol.startswith("^"):
        return {
            "function": "INDEX_DATA",
            "symbol": normalized,
            "apikey": api_key,
        }
    return {
        "function": "TIME_SERIES_DAILY",
        "symbol": normalized,
        "outputsize": "full",
        "apikey": api_key,
    }


def _raise_for_api_error(payload: dict[str, Any]) -> None:
    for key in ("Error Message", "Note", "Information"):
        if key in payload:
            raise RuntimeError(str(payload[key]))
    if not _time_series(payload):
        raise RuntimeError(f"Unexpected Alpha Vantage response keys: {list(payload.keys())}")


def _time_series(payload: dict[str, Any]) -> dict[str, Any]:
    for key, value in payload.items():
        if "Time Series" in key and isinstance(value, dict):
            return value
    return {}


def _first(values: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in values:
            return values[key]
    raise KeyError(f"Missing keys {keys}; got {list(values.keys())}")


def _optional_float(values: dict[str, Any], *keys: str) -> float | None:
    try:
        value = _first(values, *keys)
    except KeyError:
        return None
    if value in (None, ""):
        return None
    return float(value)
