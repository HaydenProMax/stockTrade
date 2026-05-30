from __future__ import annotations

from statistics import mean

from fund_signal.types import AssetSignal, PriceBar


def calculate_signal(asset_group: str, asset_config: dict, strategy_config: dict, bars: list[PriceBar]) -> AssetSignal:
    window = int(strategy_config["drawdown_window_days"])
    if len(bars) < window:
        raise ValueError(f"{asset_group} requires at least {window} bars, got {len(bars)}")

    latest = bars[-1]
    recent = bars[-window:]
    high = max(bar.high or bar.close for bar in recent)
    drawdown = latest.close / high - 1

    raw_units = _units_for_drawdown(
        drawdown,
        strategy_config["volatility_classes"][asset_config["volatility_class"]]["bands"],
    )
    trend_state, multiplier = _trend_multiplier(bars, strategy_config["trend_filter"])
    final_units = raw_units * multiplier

    return AssetSignal(
        asset_group=asset_group,
        name=asset_config["name"],
        drawdown=drawdown,
        raw_units=raw_units,
        final_units=final_units,
        trend_state=trend_state,
        reason=f"drawdown={drawdown:.2%}, raw_units={raw_units}, multiplier={multiplier}",
    )


def _units_for_drawdown(drawdown: float, bands: list[dict]) -> float:
    for band in bands:
        threshold = band["max_drawdown"]
        if threshold is None or drawdown >= float(threshold):
            return float(band["units"])
    return 0


def _trend_multiplier(bars: list[PriceBar], config: dict) -> tuple[str, float]:
    closes = [bar.close for bar in bars]
    latest = closes[-1]
    ma60 = mean(closes[-60:])
    ma120 = mean(closes[-120:])

    if latest > ma60:
        return "above_ma_60", float(config["above_ma_60_multiplier"])
    if latest > ma120:
        return "below_ma_60_above_ma_120", float(config["below_ma_60_above_ma_120_multiplier"])
    return "below_ma_120", float(config["below_ma_120_multiplier"])
