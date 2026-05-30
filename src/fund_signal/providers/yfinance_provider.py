from __future__ import annotations

from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any

import requests

from fund_signal.providers.base import MarketDataProvider
from fund_signal.types import PriceBar


class YFinanceProvider(MarketDataProvider):
    name = "yfinance"

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir

    def history(self, symbol: str, start: date | None = None, end: date | None = None) -> list[PriceBar]:
        chart_bars = _download_chart(symbol, start=start, end=end)
        if chart_bars:
            return chart_bars

        import yfinance as yf

        yfinance_cache_dir = self.cache_dir / "yfinance"
        yfinance_cache_dir.mkdir(parents=True, exist_ok=True)
        yf.set_tz_cache_location(str(yfinance_cache_dir))

        data = yf.download(
            symbol,
            start=start,
            end=end,
            progress=False,
            auto_adjust=False,
            threads=False,
        )
        if data.empty:
            return []

        bars: list[PriceBar] = []
        for index, row in data.iterrows():
            bars.append(
                PriceBar(
                    date=index.date(),
                    open=_value(row, "Open"),
                    high=_value(row, "High"),
                    low=_value(row, "Low"),
                    close=float(_value(row, "Close") or 0),
                    volume=_value(row, "Volume"),
                    source=self.name,
                )
            )
        return bars


def _download_chart(symbol: str, start: date | None, end: date | None) -> list[PriceBar]:
    params: dict[str, Any] = {"interval": "1d", "events": "history"}
    if start:
        params["period1"] = _timestamp(start)
        params["period2"] = _timestamp(end or date.today())
    if end:
        params["period2"] = _timestamp(end)
    if not start and not end:
        params["range"] = "2y"

    response = requests.get(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
        params=params,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    chart = payload.get("chart", {})
    if chart.get("error"):
        raise RuntimeError(chart["error"])
    results = chart.get("result") or []
    if not results:
        return []

    result = results[0]
    timestamps = result.get("timestamp") or []
    quotes = (result.get("indicators", {}).get("quote") or [{}])[0]
    bars: list[PriceBar] = []
    for index, timestamp in enumerate(timestamps):
        close = _item(quotes, "close", index)
        if close is None:
            continue
        bars.append(
            PriceBar(
                date=datetime.fromtimestamp(timestamp, tz=timezone.utc).date(),
                open=_item(quotes, "open", index),
                high=_item(quotes, "high", index),
                low=_item(quotes, "low", index),
                close=float(close),
                volume=_item(quotes, "volume", index),
                source="yahoo_chart",
            )
        )
    return bars


def _timestamp(value: date) -> int:
    return int(datetime.combine(value, time.min, tzinfo=timezone.utc).timestamp())


def _item(values: dict[str, list[Any]], key: str, index: int) -> float | None:
    items = values.get(key) or []
    if index >= len(items) or items[index] is None:
        return None
    return float(items[index])


def _value(row, column: str) -> float | None:
    value = row.get(column)
    if value is None:
        return None
    try:
        return float(value)
    except TypeError:
        return float(value.iloc[0])
