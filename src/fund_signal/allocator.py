from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from fund_signal.calendar import is_in_last_trading_days, is_last_trading_day
from fund_signal.types import AssetSignal, FundAllocation


@dataclass
class AllocationState:
    portfolio_remaining: float
    asset_spent: dict[str, float]
    fund_spent: dict[str, float]


def allocate_to_funds(
    asset_group: str,
    asset_config: dict,
    signal: AssetSignal,
    budget_config: dict,
    state: AllocationState,
    *,
    mode: str,
    today: date,
    calendars: dict,
    calendar_cache_dir: Path | None = None,
) -> list[FundAllocation]:
    allocations: list[FundAllocation] = []
    if state.portfolio_remaining <= 0:
        return [
            _allocation(
                asset_group,
                "ASSET_GROUP",
                asset_config["name"],
                0,
                0,
                "portfolio_limit_reached",
                "monthly portfolio hard limit reached",
            )
        ]

    execution_mode = mode in {"afternoon", "manual"}
    if not execution_mode:
        return [
            _allocation(
                asset_group,
                "ASSET_GROUP",
                asset_config["name"],
                signal.final_units,
                0,
                "observe_only",
                f"{mode} run is observation only",
            )
        ]

    for fund in _enabled_funds(asset_config):
        for plan in fund.get("plans", []):
            if plan.get("type") == "fixed_daily":
                allocations.append(
                    _fixed_allocation(asset_group, fund, plan, state, "fixed_daily")
                )
            elif plan.get("type") == "fixed_monthly":
                allocations.append(
                    _fixed_allocation(asset_group, fund, plan, state, "fixed_monthly")
                )

    strategy_plan = asset_config.get("strategy_plan")
    if strategy_plan:
        allocations.extend(
            _strategy_allocations(
                asset_group,
                asset_config,
                signal,
                strategy_plan,
                state,
                today=today,
                calendars=calendars,
                calendar_cache_dir=calendar_cache_dir,
            )
        )

    return [allocation for allocation in allocations if allocation.amount > 0 or allocation.status != "skipped"]


def _fixed_allocation(
    asset_group: str,
    fund: dict,
    plan: dict,
    state: AllocationState,
    status: str,
) -> FundAllocation:
    requested = float(plan["amount"])
    monthly_budget = float(plan.get("monthly_budget_amount", requested))
    fund_remaining = max(0.0, monthly_budget - state.fund_spent.get(fund["code"], 0.0))
    amount = _consume(state, asset_group, fund["code"], min(requested, fund_remaining))
    return _allocation(
        asset_group,
        fund["code"],
        fund["name"],
        0,
        amount,
        "assumed_executed" if amount > 0 else "skipped",
        f"{status}; requested={requested:g}; monthly_remaining={fund_remaining:g}",
    )


def _strategy_allocations(
    asset_group: str,
    asset_config: dict,
    signal: AssetSignal,
    plan: dict,
    state: AllocationState,
    *,
    today: date,
    calendars: dict,
    calendar_cache_dir: Path | None,
) -> list[FundAllocation]:
    unit_amount = float(plan["unit_amount"])
    monthly_budget = float(plan["monthly_budget_amount"])
    asset_remaining = max(0.0, monthly_budget - state.asset_spent.get(asset_group, 0.0))
    units = signal.final_units
    requested = units * unit_amount
    reason = f"strategy signal; units={units:g}; unit_amount={unit_amount:g}"

    if requested <= 0 and plan.get("month_end_fill"):
        requested, reason = _month_end_fill_amount(
            asset_group,
            signal,
            plan,
            asset_remaining,
            today,
            calendars,
            calendar_cache_dir,
        )
        units = requested / unit_amount if unit_amount else 0

    requested = min(requested, asset_remaining)
    if requested <= 0:
        return [
            _allocation(
                asset_group,
                "ASSET_GROUP",
                asset_config["name"],
                units,
                0,
                "skipped",
                f"{reason}; no strategy amount available",
            )
        ]

    funds = [
        fund for fund in _enabled_funds(asset_config)
        if fund.get("strategy_enabled", False)
    ]
    if not funds:
        return [
            _allocation(
                asset_group,
                "ASSET_GROUP",
                asset_config["name"],
                units,
                0,
                "unconfigured",
                f"{reason}; no strategy-enabled funds",
            )
        ]

    funds.sort(key=lambda fund: int(fund.get("strategy_priority", 999)))
    remaining = min(requested, state.portfolio_remaining)
    allocations: list[FundAllocation] = []
    for fund in funds:
        if remaining <= 0:
            break
        daily_limit = float(fund.get("daily_limit_amount", remaining))
        fund_amount = min(remaining, daily_limit)
        amount = _consume(state, asset_group, fund["code"], fund_amount)
        remaining -= amount
        allocations.append(
            _allocation(
                asset_group,
                fund["code"],
                fund["name"],
                units if amount > 0 else 0,
                amount,
                "assumed_executed" if amount > 0 else "skipped",
                f"{reason}; priority={fund.get('strategy_priority', '-')}; daily_limit={daily_limit:g}",
            )
        )

    deferred = requested - sum(item.amount for item in allocations)
    if deferred > 0:
        allocations.append(
            _allocation(
                asset_group,
                "ASSET_GROUP",
                asset_config["name"],
                deferred / unit_amount if unit_amount else 0,
                0,
                "deferred",
                f"{reason}; deferred_amount={deferred:g}",
            )
        )
    return allocations


def _month_end_fill_amount(
    asset_group: str,
    signal: AssetSignal,
    plan: dict,
    asset_remaining: float,
    today: date,
    calendars: dict,
    calendar_cache_dir: Path | None,
) -> tuple[float, str]:
    window = int(plan.get("fill_last_trading_days", 5))
    if not is_in_last_trading_days(today, calendars, window, calendar_cache_dir):
        return 0.0, f"month_end_fill inactive; last_{window}_trading_days_only"
    if signal.daily_change < 0:
        return asset_remaining, f"month_end_fill; negative day {signal.daily_change:.2%}"
    if is_last_trading_day(today, calendars, calendar_cache_dir):
        return asset_remaining, "month_end_fill; final trading day"
    return 0.0, f"month_end_fill waiting for negative day; daily_change={signal.daily_change:.2%}"


def _consume(
    state: AllocationState,
    asset_group: str,
    fund_code: str,
    requested: float,
) -> float:
    amount = max(0.0, min(float(requested), state.portfolio_remaining))
    state.portfolio_remaining -= amount
    state.asset_spent[asset_group] = state.asset_spent.get(asset_group, 0.0) + amount
    if fund_code != "ASSET_GROUP":
        state.fund_spent[fund_code] = state.fund_spent.get(fund_code, 0.0) + amount
    return amount


def _enabled_funds(asset_config: dict) -> list[dict]:
    return [fund for fund in asset_config.get("funds", []) if fund.get("enabled", True)]


def _allocation(
    asset_group: str,
    fund_code: str,
    fund_name: str,
    units: float,
    amount: float,
    status: str,
    reason: str,
) -> FundAllocation:
    return FundAllocation(
        asset_group=asset_group,
        fund_code=fund_code,
        fund_name=fund_name,
        units=float(units),
        amount=float(amount),
        executed_amount=float(amount) if status == "assumed_executed" else None,
        status=status,
        reason=reason,
    )
