from __future__ import annotations

from datetime import date

from fund_signal.notifier_feishu import render_message
from fund_signal.types import AssetSignal, FundAllocation


def test_render_message_groups_summary_and_readable_sections():
    message = render_message(
        "afternoon",
        [
            AssetSignal(
                asset_group="hstech",
                name="恒生科技",
                source="test",
                data_date=date(2026, 5, 29),
                drawdown=-0.2727,
                daily_change=-0.0009,
                raw_units=3,
                final_units=3,
                trend_state="below_ma_120",
                reason="debug details",
            )
        ],
        [
            FundAllocation(
                asset_group="nasdaq100",
                fund_code="040046",
                fund_name="华安纳斯达克100A",
                units=0,
                amount=10,
                executed_amount=10,
                status="assumed_executed+purchase_limited",
                reason="fixed_daily; requested=10",
            ),
            FundAllocation(
                asset_group="hstech",
                fund_code="012348",
                fund_name="恒生科技基金",
                units=3,
                amount=300,
                executed_amount=300,
                status="assumed_executed+purchase_limited",
                reason="strategy signal; units=3; unit_amount=100",
            ),
        ],
    )

    assert "【下午执行】" in message
    assert "一、今日结论" in message
    assert "二、固定定投" in message
    assert "三、策略建议" in message
    assert "资产状态" in message
    assert "建议执行：310元" in message
    assert "限购内执行" in message
    assert "debug details" not in message


def test_render_us_weekly_is_observation_only():
    message = render_message(
        "us_weekly",
        [
            AssetSignal(
                asset_group="nasdaq100",
                name="纳指100",
                source="test",
                data_date=date(2026, 5, 29),
                drawdown=-0.01,
                daily_change=0.003,
                raw_units=0,
                final_units=0,
                trend_state="above_ma_60",
                reason="debug",
            )
        ],
        [
            FundAllocation(
                asset_group="nasdaq100",
                fund_code="ASSET_GROUP",
                fund_name="纳指100",
                units=0,
                amount=0,
                executed_amount=None,
                status="dry_run:observe_only",
                reason="us_weekly run is observation only",
            )
        ],
        ["US WEEKLY: observation only; no default execution or budget usage."],
    )

    assert "【美股周收盘观察】" in message
    assert "模式：观察，不记账" in message
    assert "观察信号" in message
    assert "美股周报只观察，不执行，不占用预算" in message
