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
    drawdown: float
    raw_units: float
    final_units: float
    trend_state: str
    reason: str


@dataclass(frozen=True)
class FundAllocation:
    asset_group: str
    fund_code: str
    fund_name: str
    units: float
    status: str
    reason: str
