from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

from fund_signal.allocator import AllocationState, allocate_to_funds
from fund_signal.calendar import should_run_today, trading_day_lag
from fund_signal.config import AppConfig
from fund_signal.fund_rules import apply_purchase_rules
from fund_signal.market_data import MarketData
from fund_signal.notifier_feishu import render_message, send_text, signal_hash
from fund_signal.providers.akshare_provider import AkshareProvider
from fund_signal.strategy import (
    apply_active_qdii_confirmation,
    calculate_drawdown,
    calculate_signal,
)
from fund_signal.storage import Storage
from fund_signal.types import AssetSignal, FundAllocation, PriceBar


def run(config: AppConfig, mode: str, send: bool = False, dry_run: bool = False) -> str:
    today = date.today()
    cache_dir = config.root / "data" / "cache"
    trading_day = should_run_today(today, config.calendars, cache_dir)
    us_weekly_day = _should_run_us_weekly(today, config.calendars)
    if mode == "us_weekly" and not us_weekly_day and not dry_run:
        return f"Skip: {today.isoformat()} is not a configured US weekly observation day."
    if mode not in {"manual", "us_weekly"} and not trading_day and not dry_run:
        return f"Skip: {today.isoformat()} is not a configured trading day."

    storage = Storage(config.root / "data" / "fund_signal.sqlite")
    storage.init_schema()
    run_date = today.isoformat()
    run_id = None if dry_run else storage.start_run(run_date, mode)

    try:
        if not dry_run:
            storage.clear_run_outputs(run_date, mode)
        market_data = MarketData(cache_dir)
        monthly_total, monthly_asset_spent, monthly_fund_spent = storage.monthly_spending(
            run_date[:7]
        )
        portfolio_limit = float(config.budget.get("portfolio_monthly_hard_limit_amount", 0) or 0)
        portfolio_remaining = max(0.0, portfolio_limit - monthly_total) if portfolio_limit else float("inf")
        allocation_state = AllocationState(
            portfolio_remaining=portfolio_remaining,
            asset_spent=monthly_asset_spent,
            fund_spent=monthly_fund_spent,
        )
        signals: list[AssetSignal] = []
        allocations: list[FundAllocation] = []
        warnings: list[str] = []
        histories: dict[str, list[PriceBar]] = {}

        start = today - timedelta(days=500)
        selected_keys = {key for key, _ in _selected_asset_groups(config, mode)}
        for asset_group, asset_config in _history_asset_groups(config, mode):
            provider = asset_config.get("provider")
            if provider == "proxy":
                continue
            try:
                bars = market_data.history(
                    asset_config["index_symbol"],
                    provider,
                    start=start,
                    fallback=tuple(asset_config.get("provider_fallback", ["csv"])),
                )
            except Exception as exc:  # noqa: BLE001 - keep one provider failure from stopping all signals
                warnings.append(f"{asset_config['name']}({asset_config['index_symbol']}): {exc}")
                continue
            histories[asset_group] = bars
            if asset_group not in selected_keys:
                continue
            signal = calculate_signal(asset_group, asset_config, config.strategy, bars)
            signals.append(signal)
            if _cache_allows_strategy(signal, today, config.calendars, warnings, cache_dir):
                allocations.extend(
                    allocate_to_funds(
                        asset_group,
                        asset_config,
                        signal,
                        config.budget,
                        allocation_state,
                        mode=mode,
                        today=today,
                        calendars=config.calendars,
                        calendar_cache_dir=cache_dir,
                    )
                )

        for asset_group, asset_config in _selected_asset_groups(config, mode):
            if asset_config.get("provider") != "proxy":
                continue
            try:
                bars = _proxy_history(asset_group, asset_config, histories)
                signal = calculate_signal(asset_group, asset_config, config.strategy, bars)
                if asset_config.get("active_fund"):
                    nav_bars = _active_fund_nav_history(asset_config)
                    nav_drawdown = calculate_drawdown(
                        nav_bars,
                        int(config.strategy["drawdown_window_days"]),
                    )
                    signal = apply_active_qdii_confirmation(
                        signal,
                        nav_drawdown,
                        float(config.strategy["active_qdii"]["fund_nav_drawdown_confirm"]),
                    )
                signals.append(signal)
                if _cache_allows_strategy(signal, today, config.calendars, warnings, cache_dir):
                    allocations.extend(
                        allocate_to_funds(
                            asset_group,
                            asset_config,
                            signal,
                            config.budget,
                            allocation_state,
                            mode=mode,
                            today=today,
                            calendars=config.calendars,
                            calendar_cache_dir=cache_dir,
                        )
                    )
            except Exception as exc:  # noqa: BLE001 - proxy assets should not stop the whole run
                warnings.append(f"{asset_config['name']}: {exc}")

        allocations = apply_purchase_rules(allocations)
        if dry_run:
            warnings.insert(0, "DRY RUN: no run, signal, allocation, or execution records were saved.")
            if mode == "us_weekly":
                warnings.insert(1, "US WEEKLY: observation only; no default execution or budget usage.")
            if mode not in {"manual", "us_weekly"} and not trading_day:
                warnings.insert(1, f"DRY RUN: {today.isoformat()} is not a configured China trading day.")
            allocations = _mark_dry_run_allocations(allocations)
        else:
            storage.save_signals(run_date, mode, signals)
            storage.save_allocations(run_date, mode, allocations)
        message = render_message(mode, signals, allocations, warnings)
        if send:
            if dry_run:
                message = _send_feishu_direct(message)
            else:
                message = _send_feishu_if_needed(storage, run_date, mode, signals, allocations, message)
        if run_id is not None:
            storage.finish_run(run_id, "success")
        return message
    except Exception as exc:
        if run_id is not None:
            storage.finish_run(run_id, "failed", str(exc))
        raise


def _cache_allows_strategy(
    signal: AssetSignal,
    today: date,
    calendars: dict,
    warnings: list[str],
    cache_dir,
) -> bool:
    if signal.source != "csv":
        return True

    lag = trading_day_lag(signal.data_date, today, calendars, cache_dir)
    if lag == 0:
        warnings.append(f"{signal.name}: using cached data from {signal.data_date.isoformat()}")
        return True
    if lag == 1:
        warnings.append(
            f"{signal.name}: cached data is one China trading day stale; observation only"
        )
        return False

    warnings.append(
        f"{signal.name}: cached data is {lag} China trading days stale; strategy skipped"
    )
    return False


def _selected_asset_groups(config: AppConfig, mode: str):
    groups = config.assets["asset_groups"].items()
    if mode != "us_weekly":
        return list(groups)
    selected = set(config.calendars.get("us_weekly", {}).get("asset_groups", []))
    return [(key, value) for key, value in groups if key in selected]


def _history_asset_groups(config: AppConfig, mode: str):
    groups = dict(config.assets["asset_groups"])
    if mode != "us_weekly":
        return list(groups.items())

    selected = set(config.calendars.get("us_weekly", {}).get("asset_groups", []))
    required = set(selected)
    for key in selected:
        asset_config = groups.get(key, {})
        if asset_config.get("provider") != "proxy":
            continue
        required.update(
            dependency
            for dependency, weight in asset_config.get("proxy_weights", {}).items()
            if dependency != "cash" and float(weight) > 0
        )
    return [(key, groups[key]) for key in groups if key in required]


def _should_run_us_weekly(today: date, calendars: dict) -> bool:
    us_weekly = calendars.get("us_weekly", {})
    if today.isoformat() in us_weekly.get("manual_run_dates", []):
        return True
    return today.weekday() == int(us_weekly.get("weekday", 5))


def _mark_dry_run_allocations(allocations: list[FundAllocation]) -> list[FundAllocation]:
    return [
        replace(
            allocation,
            executed_amount=None,
            status=f"dry_run:{allocation.status}",
            reason=f"{allocation.reason}; dry run only, not recorded",
        )
        for allocation in allocations
    ]


def _send_feishu_direct(message: str) -> str:
    import os

    webhook_url = os.getenv("FEISHU_WEBHOOK_URL")
    if not webhook_url:
        raise RuntimeError("Missing FEISHU_WEBHOOK_URL in environment or .env")
    webhook_secret = os.getenv("FEISHU_WEBHOOK_SECRET") or None
    response = send_text(webhook_url, "【DRY RUN】\n" + message, webhook_secret)
    response.raise_for_status()
    return "Sent Feishu dry-run notification.\n\n" + message


def _proxy_history(asset_group: str, asset_config: dict, histories: dict[str, list[PriceBar]]) -> list[PriceBar]:
    weights = asset_config.get("proxy_weights", {})
    dependency_keys = [key for key in weights if key != "cash" and weights[key] > 0]
    if not dependency_keys:
        raise ValueError(f"{asset_group} has no non-cash proxy weights")

    dependency_histories = {key: histories[key] for key in dependency_keys if key in histories}
    missing = sorted(set(dependency_keys) - set(dependency_histories))
    if missing:
        raise ValueError(f"missing proxy histories: {', '.join(missing)}")

    common_dates = set.intersection(
        *(set(bar.date for bar in bars) for bars in dependency_histories.values())
    )
    if not common_dates:
        raise ValueError("proxy histories have no overlapping dates")

    sorted_dates = sorted(common_dates)
    by_date = {
        key: {bar.date: bar for bar in bars}
        for key, bars in dependency_histories.items()
    }
    base_close = {key: by_date[key][sorted_dates[0]].close for key in dependency_keys}

    proxy_bars: list[PriceBar] = []
    for bar_date in sorted_dates:
        close = float(weights.get("cash", 0))
        for key in dependency_keys:
            close += float(weights[key]) * by_date[key][bar_date].close / base_close[key]
        proxy_bars.append(
            PriceBar(
                date=bar_date,
                open=close,
                high=close,
                low=close,
                close=close,
                volume=None,
                source="proxy:" + "+".join(dependency_keys),
            )
        )
    return proxy_bars


def _active_fund_nav_history(asset_config: dict) -> list[PriceBar]:
    enabled_funds = [fund for fund in asset_config.get("funds", []) if fund.get("enabled", True)]
    if not enabled_funds:
        raise ValueError("active fund has no enabled funds")
    return AkshareProvider().fund_nav_history(enabled_funds[0]["code"])


def _send_feishu_if_needed(
    storage: Storage,
    run_date: str,
    mode: str,
    signals: list[AssetSignal],
    allocations: list[FundAllocation],
    message: str,
) -> str:
    import os

    webhook_url = os.getenv("FEISHU_WEBHOOK_URL")
    if not webhook_url:
        raise RuntimeError("Missing FEISHU_WEBHOOK_URL in environment or .env")
    webhook_secret = os.getenv("FEISHU_WEBHOOK_SECRET") or None

    pending: list[tuple[AssetSignal, str]] = []
    for signal in signals:
        signal_allocations = [
            allocation for allocation in allocations if allocation.asset_group == signal.asset_group
        ]
        digest = signal_hash(signal, signal_allocations)
        if not storage.notification_sent(run_date, mode, signal.asset_group, digest):
            pending.append((signal, digest))

    if not pending:
        return "Skip Feishu notification: same signals already sent.\n\n" + message

    response = send_text(webhook_url, message, webhook_secret)
    status = "success" if response.ok else "failed"
    for signal, digest in pending:
        storage.save_notification(
            run_date=run_date,
            mode=mode,
            asset_group=signal.asset_group,
            signal_hash=digest,
            status=status,
            response_code=response.status_code,
            response_body=response.text[:1000],
        )
    response.raise_for_status()
    return "Sent Feishu notification.\n\n" + message
