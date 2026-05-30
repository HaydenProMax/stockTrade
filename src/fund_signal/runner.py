from __future__ import annotations

from datetime import date, timedelta

from fund_signal.allocator import allocate_to_funds
from fund_signal.calendar import should_run_today
from fund_signal.config import AppConfig
from fund_signal.fund_rules import apply_purchase_rules
from fund_signal.market_data import MarketData
from fund_signal.notifier_feishu import render_message
from fund_signal.providers.akshare_provider import AkshareProvider
from fund_signal.strategy import (
    apply_active_qdii_confirmation,
    calculate_drawdown,
    calculate_signal,
)
from fund_signal.storage import Storage
from fund_signal.types import AssetSignal, FundAllocation, PriceBar


def run(config: AppConfig, mode: str, send: bool = False) -> str:
    today = date.today()
    if mode != "manual" and not should_run_today(today, config.calendars):
        return f"Skip: {today.isoformat()} is not a configured trading day."

    storage = Storage(config.root / "data" / "fund_signal.sqlite")
    storage.init_schema()

    market_data = MarketData(config.root / "data" / "cache")
    signals: list[AssetSignal] = []
    allocations: list[FundAllocation] = []
    warnings: list[str] = []
    histories: dict[str, list[PriceBar]] = {}

    start = today - timedelta(days=500)
    for asset_group, asset_config in config.assets["asset_groups"].items():
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
        signal = calculate_signal(asset_group, asset_config, config.strategy, bars)
        signals.append(signal)
        allocations.extend(allocate_to_funds(asset_config, signal))

    for asset_group, asset_config in config.assets["asset_groups"].items():
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
            allocations.extend(allocate_to_funds(asset_config, signal))
        except Exception as exc:  # noqa: BLE001 - proxy assets should not stop the whole run
            warnings.append(f"{asset_config['name']}: {exc}")

    allocations = apply_purchase_rules(allocations)
    message = render_message(mode, signals, allocations, warnings)
    if send:
        raise NotImplementedError("Feishu send will be enabled after webhook configuration is provided.")
    return message


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
