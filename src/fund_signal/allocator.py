from __future__ import annotations

from fund_signal.types import AssetSignal, FundAllocation


def allocate_to_funds(asset_config: dict, signal: AssetSignal) -> list[FundAllocation]:
    funds = [fund for fund in asset_config.get("funds", []) if fund.get("enabled", True)]
    if not funds:
        return []

    ratios = [fund.get("allocation_ratio") for fund in funds]
    if any(ratio is None for ratio in ratios):
        return [
            FundAllocation(
                asset_group=signal.asset_group,
                fund_code="ASSET_GROUP",
                fund_name=asset_config["name"],
                units=signal.final_units,
                status="group_only",
                reason="fund allocation ratios are not configured",
            )
        ]

    total_ratio = sum(float(ratio) for ratio in ratios)
    if total_ratio <= 0:
        raise ValueError(f"Invalid allocation ratio for {signal.asset_group}")

    allocations: list[FundAllocation] = []
    for fund, ratio in zip(funds, ratios, strict=True):
        units = signal.final_units * float(ratio) / total_ratio
        allocations.append(
            FundAllocation(
                asset_group=signal.asset_group,
                fund_code=fund["code"],
                fund_name=fund["name"],
                units=units,
                status="suggested",
                reason="allocated by configured ratio",
            )
        )
    return allocations
