from __future__ import annotations

from fund_signal.types import FundAllocation


def apply_purchase_rules(allocations: list[FundAllocation]) -> list[FundAllocation]:
    # The AKShare fund_purchase_em integration will be added behind this boundary.
    return allocations
