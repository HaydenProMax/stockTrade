from __future__ import annotations

from datetime import date
from pathlib import Path

from fund_signal.providers.akshare_provider import AkshareProvider
from fund_signal.providers.alphavantage_provider import AlphaVantageProvider
from fund_signal.providers.csv_provider import CsvProvider
from fund_signal.providers.yfinance_provider import YFinanceProvider
from fund_signal.types import PriceBar


class MarketData:
    def __init__(self, cache_dir: Path):
        self.providers = {
            "alphavantage": AlphaVantageProvider(),
            "yfinance": YFinanceProvider(cache_dir),
            "akshare": AkshareProvider(),
            "csv": CsvProvider(cache_dir),
        }

    def history(
        self,
        symbol: str,
        provider_name: str,
        start: date | None = None,
        end: date | None = None,
        fallback: tuple[str, ...] = ("csv",),
        retries: int = 3,
    ) -> list[PriceBar]:
        provider_order = (provider_name, *fallback)
        errors: list[str] = []
        for name in provider_order:
            provider = self.providers[name]
            attempts = retries if name == provider_name else 1
            for attempt in range(1, attempts + 1):
                try:
                    bars = provider.history(symbol, start=start, end=end)
                except Exception as exc:  # noqa: BLE001 - provider boundary records recoverable fetch errors
                    errors.append(f"{name} attempt {attempt}: {exc}")
                    continue
                if bars:
                    return bars
                errors.append(f"{name} attempt {attempt}: empty result")
        raise RuntimeError(f"No market data for {symbol}. Errors: {'; '.join(errors)}")
