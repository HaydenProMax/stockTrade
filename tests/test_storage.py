from __future__ import annotations

from fund_signal.storage import Storage
from fund_signal.types import FundAllocation


def test_monthly_spending_counts_purchase_augmented_assumed_execution(tmp_path):
    storage = Storage(tmp_path / "fund_signal.sqlite")
    storage.init_schema()
    storage.save_allocations(
        "2026-05-29",
        "afternoon",
        [
            FundAllocation(
                asset_group="hstech",
                fund_code="012348",
                fund_name="恒生科技",
                units=3,
                amount=300,
                executed_amount=300,
                status="assumed_executed+purchase_limited",
                reason="test",
            )
        ],
    )

    total, by_asset, by_fund = storage.monthly_spending("2026-05")

    assert total == 300
    assert by_asset == {"hstech": 300}
    assert by_fund == {"012348": 300}
