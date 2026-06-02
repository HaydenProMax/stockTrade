from __future__ import annotations

from datetime import date
from io import StringIO
import os

import requests

from fund_signal.providers.base import MarketDataProvider
from fund_signal.types import PriceBar


class StooqProvider(MarketDataProvider):
    name = "stooq"
    base_url = "https://stooq.com/q/d/l/"

    def history(self, symbol: str, start: date | None = None, end: date | None = None) -> list[PriceBar]:
        import pandas as pd

        api_key = os.getenv("STOOQ_API_KEY")
        if not api_key:
            raise RuntimeError("Missing STOOQ_API_KEY in environment or .env")

        response = requests.get(
            self.base_url,
            params={
                "s": _normalize_symbol(symbol),
                "i": "d",
                "apikey": api_key,
            },
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=30,
        )
        response.raise_for_status()

        data = pd.read_csv(StringIO(response.text))
        if data.empty or "Date" not in data.columns:
            if response.text.lower().startswith("get your apikey"):
                raise RuntimeError("Stooq API key is missing or invalid")
            return []

        bars: list[PriceBar] = []
        for _, row in data.iterrows():
            bar_date = date.fromisoformat(str(row["Date"]))
            if start and bar_date < start:
                continue
            if end and bar_date >= end:
                continue
            bars.append(
                PriceBar(
                    date=bar_date,
                    open=_optional_float(row.get("Open"), pd),
                    high=_optional_float(row.get("High"), pd),
                    low=_optional_float(row.get("Low"), pd),
                    close=float(row["Close"]),
                    volume=_optional_float(row.get("Volume"), pd),
                    source=self.name,
                )
            )
        return bars


def _normalize_symbol(symbol: str) -> str:
    aliases = {
        "QQQ": "qqq.us",
        "SPY": "spy.us",
        "1321.T": "1321.jp",
    }
    return aliases.get(symbol, symbol.lower())


def _optional_float(value, pd) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)
