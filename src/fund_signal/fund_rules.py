from __future__ import annotations

from dataclasses import replace

from fund_signal.providers.akshare_provider import AkshareProvider
from fund_signal.types import FundAllocation


def apply_purchase_rules(allocations: list[FundAllocation]) -> list[FundAllocation]:
    status_by_code = _purchase_status_by_code()
    if not status_by_code:
        return [
            replace(
                allocation,
                status=_status_with_purchase(allocation.status, "purchase_status_unknown"),
                reason=f"{allocation.reason}; purchase status unavailable",
            )
            if allocation.fund_code != "ASSET_GROUP"
            else allocation
            for allocation in allocations
        ]

    checked: list[FundAllocation] = []
    for allocation in allocations:
        if allocation.fund_code == "ASSET_GROUP":
            checked.append(allocation)
            continue

        status = status_by_code.get(allocation.fund_code)
        if status is None:
            checked.append(
                replace(
                    allocation,
                    status=_status_with_purchase(allocation.status, "purchase_status_unknown"),
                    reason=f"{allocation.reason}; purchase status not found",
                )
            )
            continue

        fund_name = str(_first_existing(status, ["基金简称", "fund_name"], allocation.fund_name)).strip()
        purchase_status = str(_first_existing(status, ["申购状态", "purchase_status"], "")).strip()
        daily_limit_value = _daily_limit_value(_first_existing(status, ["日累计限定金额", "daily_limit"], None))

        if "暂停" in purchase_status:
            checked.append(
                replace(
                    allocation,
                    fund_name=fund_name or allocation.fund_name,
                    units=0,
                    amount=0,
                    executed_amount=None,
                    status="purchase_suspended",
                    reason=f"purchase status: {purchase_status}",
                )
            )
        elif "限" in purchase_status or daily_limit_value is not None:
            checked.append(
                replace(
                    allocation,
                    fund_name=fund_name or allocation.fund_name,
                    status=_status_with_purchase(allocation.status, "purchase_limited"),
                    reason=(
                        f"{allocation.reason}; purchase status: {purchase_status or 'unknown'}; "
                        f"daily_limit={daily_limit_value if daily_limit_value is not None else 'unknown'}"
                    ),
                )
            )
        else:
            checked.append(
                replace(
                    allocation,
                    fund_name=fund_name or allocation.fund_name,
                    status=_status_with_purchase(allocation.status, "purchase_open"),
                    reason=f"{allocation.reason}; purchase status: {purchase_status or 'unknown'}",
                )
            )
    return checked


def _purchase_status_by_code() -> dict[str, dict]:
    try:
        data = AkshareProvider().fund_purchase_status()
    except Exception:  # noqa: BLE001 - purchase status is advisory
        return {}
    if data is None or data.empty:
        return {}

    result: dict[str, dict] = {}
    for _, row in data.iterrows():
        code = str(_first_existing(row, ["基金代码", "code"], "")).zfill(6)
        if code:
            result[code] = row.to_dict()
    return result


def _first_existing(row, keys: list[str], default):
    for key in keys:
        if key in row:
            return row[key]
    return default


def _daily_limit_value(value) -> float | None:
    if value in (None, "", "-", "--"):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric <= 0:
        return None
    if numeric >= 10_000_000_000:
        return None
    return numeric


def _status_with_purchase(current_status: str, purchase_status: str) -> str:
    if current_status == "assumed_executed":
        return f"{current_status}+{purchase_status}"
    return current_status
