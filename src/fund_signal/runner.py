from __future__ import annotations

from datetime import date, timedelta

from fund_signal.allocator import allocate_to_funds
from fund_signal.calendar import should_run_today
from fund_signal.config import AppConfig
from fund_signal.fund_rules import apply_purchase_rules
from fund_signal.market_data import MarketData
from fund_signal.notifier_feishu import render_message
from fund_signal.strategy import calculate_signal
from fund_signal.storage import Storage
from fund_signal.types import AssetSignal, FundAllocation


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
        signal = calculate_signal(asset_group, asset_config, config.strategy, bars)
        signals.append(signal)
        allocations.extend(allocate_to_funds(asset_config, signal))

    allocations = apply_purchase_rules(allocations)
    message = render_message(mode, signals, allocations, warnings)
    if send:
        raise NotImplementedError("Feishu send will be enabled after webhook configuration is provided.")
    return message
