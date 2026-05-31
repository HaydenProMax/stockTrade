from __future__ import annotations

from datetime import date

from fund_signal.allocator import AllocationState, allocate_to_funds
from fund_signal.types import AssetSignal


def test_global_tech_prefers_a_class_and_defers_over_daily_limits():
    config = {
        "name": "全球科技互联",
        "strategy_plan": {"monthly_budget_amount": 1000, "unit_amount": 100},
        "funds": [
            {
                "code": "006373",
                "name": "A",
                "enabled": True,
                "strategy_enabled": True,
                "strategy_priority": 1,
                "daily_limit_amount": 100,
            },
            {
                "code": "021842",
                "name": "C",
                "enabled": True,
                "strategy_enabled": True,
                "strategy_priority": 2,
                "daily_limit_amount": 100,
            },
        ],
    }
    signal = _signal("global_tech", final_units=3)
    state = AllocationState(portfolio_remaining=5500, asset_spent={}, fund_spent={})

    allocations = allocate_to_funds(
        "global_tech",
        config,
        signal,
        {},
        state,
        mode="afternoon",
        today=date(2026, 5, 29),
        calendars={},
    )

    assert [(item.fund_code, item.amount, item.status) for item in allocations] == [
        ("006373", 100, "assumed_executed"),
        ("021842", 100, "assumed_executed"),
        ("ASSET_GROUP", 0, "deferred"),
    ]
    assert allocations[2].reason.endswith("deferred_amount=100")


def test_portfolio_hard_limit_caps_strategy_amount():
    config = {
        "name": "恒生科技",
        "strategy_plan": {"monthly_budget_amount": 500, "unit_amount": 100},
        "funds": [
            {
                "code": "012348",
                "name": "恒生科技",
                "enabled": True,
                "strategy_enabled": True,
                "strategy_priority": 1,
            }
        ],
    }
    signal = _signal("hstech", final_units=3)
    state = AllocationState(portfolio_remaining=50, asset_spent={}, fund_spent={})

    allocations = allocate_to_funds(
        "hstech",
        config,
        signal,
        {},
        state,
        mode="afternoon",
        today=date(2026, 5, 29),
        calendars={},
    )

    assert allocations[0].fund_code == "012348"
    assert allocations[0].amount == 50
    assert allocations[0].executed_amount == 50
    assert allocations[1].fund_code == "ASSET_GROUP"
    assert allocations[1].status == "deferred"


def test_nasdaq_month_end_fill_buys_remaining_on_negative_day():
    config = {
        "name": "纳指100",
        "strategy_plan": {
            "monthly_budget_amount": 400,
            "unit_amount": 100,
            "month_end_fill": True,
            "fill_last_trading_days": 5,
        },
        "funds": [
            {
                "code": "021778",
                "name": "广发F",
                "enabled": True,
                "strategy_enabled": True,
                "strategy_priority": 1,
            }
        ],
    }
    signal = _signal("nasdaq100", final_units=0, daily_change=-0.01)
    state = AllocationState(portfolio_remaining=5500, asset_spent={}, fund_spent={})

    allocations = allocate_to_funds(
        "nasdaq100",
        config,
        signal,
        {},
        state,
        mode="afternoon",
        today=date(2026, 5, 29),
        calendars={},
    )

    assert allocations[0].fund_code == "021778"
    assert allocations[0].amount == 400
    assert "month_end_fill" in allocations[0].reason


def test_noon_mode_is_observation_only():
    config = {
        "name": "中证A500",
        "strategy_plan": {"monthly_budget_amount": 500, "unit_amount": 100},
        "funds": [
            {
                "code": "022459",
                "name": "中证A500",
                "enabled": True,
                "strategy_enabled": True,
                "strategy_priority": 1,
            }
        ],
    }
    signal = _signal("csi_a500", final_units=2)
    state = AllocationState(portfolio_remaining=5500, asset_spent={}, fund_spent={})

    allocations = allocate_to_funds(
        "csi_a500",
        config,
        signal,
        {},
        state,
        mode="noon",
        today=date(2026, 5, 29),
        calendars={},
    )

    assert allocations[0].fund_code == "ASSET_GROUP"
    assert allocations[0].amount == 0
    assert allocations[0].status == "observe_only"


def test_us_weekly_mode_is_observation_only():
    config = {
        "name": "纳指100",
        "strategy_plan": {"monthly_budget_amount": 400, "unit_amount": 100},
        "funds": [
            {
                "code": "021778",
                "name": "广发F",
                "enabled": True,
                "strategy_enabled": True,
                "strategy_priority": 1,
            }
        ],
    }
    signal = _signal("nasdaq100", final_units=2)
    state = AllocationState(portfolio_remaining=5500, asset_spent={}, fund_spent={})

    allocations = allocate_to_funds(
        "nasdaq100",
        config,
        signal,
        {},
        state,
        mode="us_weekly",
        today=date(2026, 6, 6),
        calendars={},
    )

    assert allocations[0].fund_code == "ASSET_GROUP"
    assert allocations[0].amount == 0
    assert allocations[0].executed_amount is None
    assert allocations[0].status == "observe_only"
    assert "us_weekly" in allocations[0].reason


def test_fixed_monthly_skips_after_fund_spent_this_month():
    config = {
        "name": "红利低波50",
        "funds": [
            {
                "code": "008163",
                "name": "红利低波",
                "enabled": True,
                "plans": [
                    {
                        "type": "fixed_monthly",
                        "amount": 1000,
                        "monthly_budget_amount": 1000,
                    }
                ],
            }
        ],
    }
    signal = _signal("dividend_low_vol_50", final_units=0)
    state = AllocationState(
        portfolio_remaining=5500,
        asset_spent={},
        fund_spent={"008163": 1000},
    )

    allocations = allocate_to_funds(
        "dividend_low_vol_50",
        config,
        signal,
        {},
        state,
        mode="afternoon",
        today=date(2026, 5, 29),
        calendars={},
    )

    assert allocations == []


def _signal(asset_group: str, final_units: float, daily_change: float = 0.0) -> AssetSignal:
    return AssetSignal(
        asset_group=asset_group,
        name=asset_group,
        source="test",
        data_date=date(2026, 5, 29),
        drawdown=-0.2,
        daily_change=daily_change,
        raw_units=final_units,
        final_units=final_units,
        trend_state="below_ma_120",
        reason="test",
    )
