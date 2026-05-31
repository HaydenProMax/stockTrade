from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class PriceBar:
    date: date
    open: float | None
    high: float | None
    low: float | None
    close: float
    volume: float | None
    source: str


@dataclass(frozen=True)
class AssetSignal:
    asset_group: str
    name: str
    source: str
    data_date: date
    drawdown: float
    daily_change: float
    raw_units: float
    final_units: float
    trend_state: str
    reason: str
    days_since_peak: int = 0
    duration_multiplier: float = 1.0


@dataclass(frozen=True)
class FundAllocation:
    asset_group: str
    fund_code: str
    fund_name: str
    units: float
    amount: float
    executed_amount: float | None
    status: str
    reason: str
