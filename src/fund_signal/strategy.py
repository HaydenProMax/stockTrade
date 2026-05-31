from __future__ import annotations

from dataclasses import replace
from statistics import mean

from fund_signal.types import AssetSignal, PriceBar


def calculate_signal(asset_group: str, asset_config: dict, strategy_config: dict, bars: list[PriceBar]) -> AssetSignal:
    window = int(strategy_config["drawdown_window_days"])
    if len(bars) < window:
        raise ValueError(f"{asset_group} requires at least {window} bars, got {len(bars)}")

    latest = bars[-1]
    previous = bars[-2] if len(bars) >= 2 else latest
    drawdown, days_since_peak = calculate_drawdown_state(bars, window)
    daily_change = latest.close / previous.close - 1 if previous.close else 0.0
    raw_units = _units_for_drawdown(
        drawdown,
        strategy_config["volatility_classes"][asset_config["volatility_class"]]["bands"],
    )
    trend_state, multiplier = _trend_multiplier(bars, strategy_config["trend_filter"])
    duration_multiplier = _duration_multiplier(
        raw_units,
        days_since_peak,
        asset_config["volatility_class"],
        strategy_config.get("drawdown_duration_adjustment", {}),
    )
    final_units = raw_units * multiplier * duration_multiplier

    return AssetSignal(
        asset_group=asset_group,
        name=asset_config["name"],
        source=latest.source,
        data_date=latest.date,
        drawdown=drawdown,
        daily_change=daily_change,
        days_since_peak=days_since_peak,
        duration_multiplier=duration_multiplier,
        raw_units=raw_units,
        final_units=final_units,
        trend_state=trend_state,
        reason=(
            f"data_date={latest.date.isoformat()}, drawdown={drawdown:.2%}, "
            f"daily_change={daily_change:.2%}, raw_units={raw_units}, "
            f"trend_multiplier={multiplier}, days_since_peak={days_since_peak}, "
            f"duration_multiplier={duration_multiplier}"
        ),
    )


def calculate_drawdown(bars: list[PriceBar], window: int) -> float:
    drawdown, _ = calculate_drawdown_state(bars, window)
    return drawdown


def calculate_drawdown_state(bars: list[PriceBar], window: int) -> tuple[float, int]:
    if len(bars) < window:
        raise ValueError(f"Requires at least {window} bars, got {len(bars)}")
    latest = bars[-1]
    recent = bars[-window:]
    high = max(bar.high or bar.close for bar in recent)
    peak_index = max(
        range(len(recent)),
        key=lambda index: recent[index].high or recent[index].close,
    )
    days_since_peak = len(recent) - 1 - peak_index
    return latest.close / high - 1, days_since_peak


def apply_active_qdii_confirmation(
    signal: AssetSignal,
    fund_nav_drawdown: float,
    confirm_threshold: float,
) -> AssetSignal:
    if signal.final_units <= 0:
        return replace(signal, reason=f"{signal.reason}; fund_nav_drawdown={fund_nav_drawdown:.2%}")
    if fund_nav_drawdown <= confirm_threshold:
        return replace(
            signal,
            reason=f"{signal.reason}; fund_nav_drawdown={fund_nav_drawdown:.2%}, confirmed",
        )
    return replace(
        signal,
        final_units=0,
        reason=(
            f"{signal.reason}; fund_nav_drawdown={fund_nav_drawdown:.2%}, "
            f"not confirmed by threshold {confirm_threshold:.2%}"
        ),
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


def _duration_multiplier(
    raw_units: float,
    days_since_peak: int,
    volatility_class: str,
    config: dict,
) -> float:
    if not config.get("enabled", False):
        return 1.0
    if config.get("only_when_raw_units_positive", True) and raw_units <= 0:
        return 1.0

    expected_days = float(config.get("expected_recovery_days", {}).get(volatility_class, 180))
    if expected_days <= 0:
        return 1.0

    ratio = days_since_peak / expected_days
    if ratio < float(config.get("early_ratio", 0.25)):
        return float(config.get("early_multiplier", 0.5))
    if ratio > float(config.get("late_ratio", 0.75)):
        return float(config.get("late_multiplier", 1.2))
    return float(config.get("normal_multiplier", 1.0))
