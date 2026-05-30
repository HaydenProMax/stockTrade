from __future__ import annotations

import hashlib
import json

from fund_signal.types import FundAllocation, AssetSignal


def signal_hash(signal: AssetSignal, allocations: list[FundAllocation]) -> str:
    payload = {
        "asset_group": signal.asset_group,
        "source": signal.source,
        "drawdown": round(signal.drawdown, 6),
        "raw_units": signal.raw_units,
        "final_units": signal.final_units,
        "trend_state": signal.trend_state,
        "allocations": [(item.fund_code, item.units, item.status) for item in allocations],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def render_message(
    mode: str,
    signals: list[AssetSignal],
    allocations: list[FundAllocation],
    warnings: list[str] | None = None,
) -> str:
    title = "午间观察" if mode == "noon" else "下午执行"
    lines = [f"【{title}】指数基金策略信号", ""]
    lines.append("资产组信号：")
    for signal in signals:
        lines.append(
            f"- {signal.name}: 回撤 {signal.drawdown:.2%}, "
            f"触发 {signal.raw_units:g}U, 建议 {signal.final_units:g}U, "
            f"{signal.trend_state}, 来源 {signal.source}"
        )
    lines.append("")
    lines.append("基金建议：")
    for allocation in allocations:
        display_name = (
            allocation.fund_name
            if allocation.fund_code == "ASSET_GROUP"
            else f"{allocation.fund_name}（{allocation.fund_code}）"
        )
        lines.append(
            f"- {display_name}: {allocation.units:g}U ({allocation.status})；{allocation.reason}"
        )
    if warnings:
        lines.append("")
        lines.append("数据警告：")
        for warning in warnings:
            lines.append(f"- {warning}")
    return "\n".join(lines)


def send_text(webhook_url: str, text: str):
    import requests

    return requests.post(webhook_url, json={"msg_type": "text", "content": {"text": text}}, timeout=10)
