from __future__ import annotations

from dataclasses import replace

from fund_signal.providers.akshare_provider import AkshareProvider
from fund_signal.types import FundAllocation


def apply_purchase_rules(allocations: list[FundAllocation]) -> list[FundAllocation]:
    status_by_code = _purchase_status_by_code()
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
                    status="purchase_status_unknown",
                    reason=f"{allocation.reason}; 申购状态未确认",
                )
            )
            continue

        fund_name = str(status.get("基金简称", allocation.fund_name)).strip() or allocation.fund_name
        purchase_status = str(status.get("申购状态", "")).strip()
        daily_limit_value = _daily_limit_value(status.get("日累计限定金额"))
        if "暂停" in purchase_status:
            checked.append(
                replace(
                    allocation,
                    fund_name=fund_name,
                    units=0,
                    status="purchase_suspended",
                    reason=f"申购状态：{purchase_status}",
                )
            )
        elif "限" in purchase_status or daily_limit_value is not None:
            checked.append(
                replace(
                    allocation,
                    fund_name=fund_name,
                    status=_status_with_purchase(allocation.status, "purchase_limited"),
                    reason=(
                        f"{allocation.reason}；申购状态：{purchase_status or '未知'}"
                        f"；日累计限定金额：{daily_limit_value:g}元"
                    ),
                )
            )
        else:
            checked.append(
                replace(
                    allocation,
                    fund_name=fund_name,
                    status=_status_with_purchase(allocation.status, "purchase_open"),
                    reason=f"{allocation.reason}；申购状态：{purchase_status or '未知'}",
                )
            )
    return checked


def _purchase_status_by_code() -> dict[str, dict]:
    try:
        data = AkshareProvider().fund_purchase_status()
    except Exception:  # noqa: BLE001 - purchase status is advisory, do not block strategy output
        return {}
    if data is None or data.empty:
        return {}

    result: dict[str, dict] = {}
    for _, row in data.iterrows():
        code = str(row.get("基金代码", "")).zfill(6)
        if code:
            result[code] = row.to_dict()
    return result


def _daily_limit_value(value) -> float | None:
    if value in (None, "", "-", "--"):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric <= 0:
        return None
    # Eastmoney commonly uses very large numbers as a practical "no limit" sentinel.
    if numeric >= 10_000_000_000:
        return None
    return numeric


def _status_with_purchase(current_status: str, purchase_status: str) -> str:
    if current_status == "suggested":
        return purchase_status
    return current_status
