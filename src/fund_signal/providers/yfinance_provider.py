from __future__ import annotations

from datetime import date

from fund_signal.providers.base import MarketDataProvider
from fund_signal.types import PriceBar


class YFinanceProvider(MarketDataProvider):
    name = "yfinance"

    def history(self, symbol: str, start: date | None = None, end: date | None = None) -> list[PriceBar]:
        import yfinance as yf

        data = yf.download(symbol, start=start, end=end, progress=False, auto_adjust=False)
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


def _value(row, column: str) -> float | None:
    value = row.get(column)
    if value is None:
        return None
    try:
        return float(value)
    except TypeError:
        return float(value.iloc[0])
