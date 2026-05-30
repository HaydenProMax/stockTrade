from __future__ import annotations

from datetime import date
from pathlib import Path

from fund_signal.providers.base import MarketDataProvider
from fund_signal.types import PriceBar


class CsvProvider(MarketDataProvider):
    name = "csv"

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir

    def history(self, symbol: str, start: date | None = None, end: date | None = None) -> list[PriceBar]:
        import pandas as pd

        path = self.cache_dir / f"{symbol.replace('^', '')}.csv"
        if not path.exists():
            return []
        data = pd.read_csv(path)
        bars: list[PriceBar] = []
        for _, row in data.iterrows():
            bar_date = date.fromisoformat(str(row["date"]))
            if start and bar_date < start:
                continue
            if end and bar_date >= end:
                continue
            bars.append(
                PriceBar(
                    date=bar_date,
                    open=_optional_float(row.get("open"), pd),
                    high=_optional_float(row.get("high"), pd),
                    low=_optional_float(row.get("low"), pd),
                    close=float(row["close"]),
                    volume=_optional_float(row.get("volume"), pd),
                    source=self.name,
                )
            )
        return bars


def _optional_float(value, pd) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)
