from __future__ import annotations

from fund_signal.fund_rules import apply_purchase_rules
from fund_signal.types import FundAllocation


def test_purchase_daily_limit_caps_amount(monkeypatch):
    monkeypatch.setattr(
        "fund_signal.fund_rules._purchase_status_by_code",
        lambda: {
            "012348": {
                "基金代码": "012348",
                "基金简称": "恒生科技",
                "申购状态": "限大额",
                "日累计限定金额": 100,
            }
        },
    )

    [allocation] = apply_purchase_rules(
        [
            FundAllocation(
                asset_group="hstech",
                fund_code="012348",
                fund_name="恒生科技",
                units=3,
                amount=300,
                executed_amount=300,
                status="assumed_executed",
                reason="strategy signal",
            )
        ]
    )

    assert allocation.amount == 100
    assert allocation.executed_amount == 100
    assert allocation.units == 1
    assert allocation.status == "assumed_executed+purchase_limited"
    assert "deferred_by_purchase_limit=200" in allocation.reason
