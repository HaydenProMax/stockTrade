from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from fund_signal.types import PriceBar


class MarketDataProvider(ABC):
    name: str

    @abstractmethod
    def history(self, symbol: str, start: date | None = None, end: date | None = None) -> list[PriceBar]:
        """Return daily price bars."""
