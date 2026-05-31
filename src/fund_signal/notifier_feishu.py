from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from fund_signal.types import AssetSignal, FundAllocation


def signal_hash(signal: AssetSignal, allocations: list[FundAllocation]) -> str:
    payload = {
        "asset_group": signal.asset_group,
        "source": signal.source,
        "data_date": signal.data_date.isoformat(),
        "drawdown": round(signal.drawdown, 6),
        "daily_change": round(signal.daily_change, 6),
        "days_since_peak": signal.days_since_peak,
        "duration_multiplier": signal.duration_multiplier,
        "raw_units": signal.raw_units,
        "final_units": signal.final_units,
        "trend_state": signal.trend_state,
        "allocations": [
            (item.fund_code, item.units, item.amount, item.status) for item in allocations
        ],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def render_message(
    mode: str,
    signals: list[AssetSignal],
    allocations: list[FundAllocation],
    warnings: list[str] | None = None,
) -> str:
    warnings = warnings or []
    title = _title(mode)
    data_date = _latest_data_date(signals)
    total_executed = sum(item.executed_amount or 0 for item in allocations)
    total_suggested = sum(item.amount for item in allocations)
    actionable = [
        item for item in allocations
        if item.amount > 0 and not item.status.startswith("dry_run:")
    ]
    dry_run = any(item.status.startswith("dry_run:") for item in allocations) or any(
        "DRY RUN" in warning for warning in warnings
    )
    observation_only = mode in {"noon", "us_weekly"} or dry_run

    lines = [
        f"【{title}】",
        f"数据日：{data_date}",
        f"模式：{'观察，不记账' if observation_only else '默认按建议执行'}",
        "",
        "一、今日结论",
    ]

    if observation_only:
        lines.append(f"- 观察金额：{_money(total_suggested)}，默认执行：0元")
    elif actionable:
        lines.append(f"- 建议执行：{_money(total_executed)}")
    else:
        lines.append("- 暂无需要执行的策略买入")

    triggered = [signal for signal in signals if signal.final_units > 0]
    if triggered:
        lines.append("- 触发资产：" + "、".join(signal.name for signal in triggered))
    else:
        lines.append("- 回撤策略：暂无新增触发")

    warning_lines = _friendly_warnings(warnings)
    if warning_lines:
        lines.append(f"- 注意事项：{warning_lines[0]}")

    fixed_allocations = _fixed_allocations(allocations)
    strategy_allocations = _strategy_allocations(allocations)
    deferred_allocations = [item for item in allocations if _base_status(item) == "deferred"]
    observation_allocations = [
        item for item in allocations
        if _base_status(item) == "observe_only" and item.amount == 0
    ]

    if fixed_allocations:
        lines.extend(["", "二、固定定投"])
        for item in fixed_allocations:
            lines.append(f"- {_fund_label(item)}：{_money(item.amount)}")

    if strategy_allocations:
        lines.extend(["", "三、策略建议"])
        for item in strategy_allocations:
            signal = _signal_for(signals, item.asset_group)
            lines.append(
                f"- {_fund_label(item)}：{_money(item.amount)}"
                f"｜{_signal_brief(signal)}｜{_status_label(item)}"
            )

    if deferred_allocations:
        lines.extend(["", "四、顺延/未执行"])
        for item in deferred_allocations:
            lines.append(f"- {item.fund_name}：顺延 {_units_text(item.units)}")

    if observation_allocations and not strategy_allocations:
        lines.extend(["", "二、观察信号"])
        for item in observation_allocations:
            signal = _signal_for(signals, item.asset_group)
            lines.append(f"- {item.fund_name}：{_signal_brief(signal)}")

    lines.extend(["", "资产状态"])
    for signal in signals:
        lines.append(
            f"- {signal.name}：日涨跌 {signal.daily_change:.2%}｜"
            f"回撤 {signal.drawdown:.2%}｜档位 {signal.final_units:g}U｜"
            f"{_trend_label(signal.trend_state)}｜距高点{signal.days_since_peak}日｜"
            f"修复系数{signal.duration_multiplier:g}"
        )

    if warning_lines:
        lines.extend(["", "数据/执行提示"])
        for warning in warning_lines:
            lines.append(f"- {warning}")

    if not observation_only:
        lines.extend(["", f"本次默认执行合计：{_money(total_executed)}"])

    return "\n".join(lines)


def send_text(webhook_url: str, text: str, secret: str | None = None):
    import requests

    payload = {"msg_type": "text", "content": {"text": text}}
    if secret:
        timestamp = str(int(time.time()))
        payload["timestamp"] = timestamp
        payload["sign"] = _feishu_sign(timestamp, secret)
    return requests.post(webhook_url, json=payload, timeout=10)


def _title(mode: str) -> str:
    return {
        "noon": "中午观察",
        "afternoon": "下午执行",
        "us_weekly": "美股周收盘观察",
        "manual": "手动运行",
    }.get(mode, "策略运行")


def _latest_data_date(signals: list[AssetSignal]) -> str:
    if not signals:
        return "无数据"
    return max(signal.data_date for signal in signals).isoformat()


def _fixed_allocations(allocations: list[FundAllocation]) -> list[FundAllocation]:
    return [
        item for item in allocations
        if item.amount > 0 and ("fixed_daily" in item.reason or "fixed_monthly" in item.reason)
    ]


def _strategy_allocations(allocations: list[FundAllocation]) -> list[FundAllocation]:
    fixed = set(id(item) for item in _fixed_allocations(allocations))
    return [
        item for item in allocations
        if item.amount > 0 and id(item) not in fixed
    ]


def _signal_for(signals: list[AssetSignal], asset_group: str) -> AssetSignal | None:
    for signal in signals:
        if signal.asset_group == asset_group:
            return signal
    return None


def _signal_brief(signal: AssetSignal | None) -> str:
    if signal is None:
        return "无信号数据"
    return (
        f"回撤 {signal.drawdown:.2%}，{_trend_label(signal.trend_state)}，"
        f"距高点{signal.days_since_peak}日，修复系数{signal.duration_multiplier:g}"
    )


def _trend_label(trend_state: str) -> str:
    return {
        "above_ma_60": "高于60日线",
        "below_ma_60_above_ma_120": "跌破60日线",
        "below_ma_120": "跌破120日线",
    }.get(trend_state, trend_state)


def _status_label(allocation: FundAllocation) -> str:
    status = allocation.status.removeprefix("dry_run:")
    labels = {
        "assumed_executed": "默认已执行",
        "purchase_limited": "限购内执行",
        "purchase_open": "开放申购",
        "purchase_status_unknown": "申购状态未知",
        "purchase_suspended": "暂停申购",
        "deferred": "顺延",
        "observe_only": "观察",
    }
    if "purchase_limited" in status:
        return "限购内执行"
    if "purchase_open" in status:
        return "开放申购"
    if "purchase_status_unknown" in status:
        return "申购状态未知"
    return labels.get(_base_status(allocation), status)


def _base_status(allocation: FundAllocation) -> str:
    status = allocation.status.removeprefix("dry_run:")
    if "+" in status:
        return status.split("+", 1)[0] if status.startswith("assumed_executed") else status
    return status


def _fund_label(allocation: FundAllocation) -> str:
    if allocation.fund_code == "ASSET_GROUP":
        return allocation.fund_name
    return f"{allocation.fund_name}（{allocation.fund_code}）"


def _money(value: float) -> str:
    if value == int(value):
        return f"{int(value)}元"
    return f"{value:.2f}元"


def _units_text(value: float) -> str:
    return f"{value:g}U"


def _friendly_warnings(warnings: list[str]) -> list[str]:
    result: list[str] = []
    for warning in warnings:
        if warning.startswith("DRY RUN: no run"):
            result.append("当前为演练模式，不写入执行记录，也不占用月预算")
        elif warning.startswith("DRY RUN:") and "not a configured China trading day" in warning:
            result.append("今天不是中国交易日，本次只做演练观察")
        elif warning.startswith("US WEEKLY:"):
            result.append("美股周报只观察，不执行，不占用预算")
        elif "cached data" in warning:
            result.append("部分数据来自缓存，请留意时效")
        else:
            result.append(warning)
    return result


def _feishu_sign(timestamp: str, secret: str) -> str:
    string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
    digest = hmac.new(string_to_sign, b"", digestmod=hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")
