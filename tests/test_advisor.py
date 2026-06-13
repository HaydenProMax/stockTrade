from __future__ import annotations

from datetime import date
from pathlib import Path

from fund_signal.advisor import answer_local_question
from fund_signal.config import AppConfig
from fund_signal.storage import Storage
from fund_signal.types import AssetSignal, FundAllocation


def test_answer_local_question_matches_fund_and_latest_allocation(tmp_path):
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    (knowledge_dir / "personal_strategy.md").write_text(
        "# 个人策略\n\n## 纳指100\n\n021778 月末补投规则。",
        encoding="utf-8",
    )
    config = _config(tmp_path)
    storage = Storage(tmp_path / "data" / "fund_signal.sqlite")
    storage.init_schema()
    run_id = storage.start_run("2026-06-03", "manual")
    storage.save_signals(
        "2026-06-03",
        "manual",
        [
            AssetSignal(
                asset_group="nasdaq100",
                name="纳指100",
                source="test",
                data_date=date(2026, 6, 2),
                drawdown=-0.16,
                daily_change=-0.01,
                raw_units=1,
                final_units=1,
                trend_state="below_ma_120",
                reason="test",
            )
        ],
    )
    storage.save_allocations(
        "2026-06-03",
        "manual",
        [
            FundAllocation(
                asset_group="nasdaq100",
                fund_code="021778",
                fund_name="广发纳斯达克100F",
                units=1,
                amount=100,
                executed_amount=100,
                status="assumed_executed",
                reason="strategy signal",
            )
        ],
    )
    storage.finish_run(run_id, "success")

    answer = answer_local_question(config, "今天 021778 要买吗？")

    assert "纳指100 (`nasdaq100`)" in answer
    assert "回撤：-16.00%" in answer
    assert "默认执行金额 100 元" in answer
    assert "| 021778 | 100 | assumed_executed | strategy signal |" in answer
    assert "## 相关知识片段" in answer
    assert "021778 月末补投规则" in answer


def test_answer_local_question_lists_assets_when_no_match(tmp_path):
    answer = answer_local_question(_config(tmp_path), "今天要干什么？")

    assert "没有从问题中识别到具体资产组或基金代码" in answer
    assert "纳指100 (`nasdaq100`)" in answer


def test_answer_local_question_reports_archived_fund_without_retrieval(tmp_path):
    config = _config(tmp_path)
    config.assets["asset_groups"]["nasdaq100"]["funds"][0]["enabled"] = False
    config.assets["asset_groups"]["nasdaq100"]["funds"][0]["archived_reason"] = (
        "not_in_long_term_holdings_2026_06_13"
    )
    records_dir = tmp_path / "strategy_records"
    records_dir.mkdir()
    (records_dir / "old.md").write_text("# 旧策略\n\n021778 月末补投。", encoding="utf-8")

    answer = answer_local_question(config, "今天 021778 要买吗？")

    assert "## 归档基金" in answer
    assert "021778 广发纳斯达克100F" in answer
    assert "相关知识片段" not in answer
    assert "月末补投" not in answer


def test_answer_local_question_filters_allocation_to_matched_fund(tmp_path):
    config = _config(tmp_path)
    storage = Storage(tmp_path / "data" / "fund_signal.sqlite")
    storage.init_schema()
    run_id = storage.start_run("2026-06-03", "manual")
    storage.save_allocations(
        "2026-06-03",
        "manual",
        [
            FundAllocation(
                asset_group="nasdaq100",
                fund_code="040046",
                fund_name="华安纳斯达克100A",
                units=0,
                amount=10,
                executed_amount=10,
                status="assumed_executed",
                reason="fixed_daily",
            )
        ],
    )
    storage.finish_run(run_id, "success")

    answer = answer_local_question(config, "今天 021778 要买吗？")

    assert "最近一次运行没有匹配基金 021778 的 allocation" in answer
    assert "默认执行金额 10 元" not in answer


def test_answer_local_question_prioritizes_matched_fund_doc(tmp_path):
    fund_docs = tmp_path / "knowledge" / "external" / "fund_docs"
    fund_docs.mkdir(parents=True)
    (fund_docs / "021778.md").write_text(
        "# 021778 广发纳斯达克100F\n\n## 费用\n\n官方基金文件中的费用信息。",
        encoding="utf-8",
    )

    answer = answer_local_question(_config(tmp_path), "021778 费用")

    fund_doc_display_path = str(Path("knowledge") / "external" / "fund_docs" / "021778.md")
    assert f"来源：`{fund_doc_display_path}`" in answer
    assert "官方基金文件中的费用信息" in answer


def _config(root) -> AppConfig:
    return AppConfig(
        root=root,
        assets={
            "asset_groups": {
                "nasdaq100": {
                    "name": "纳指100",
                    "market": "us",
                    "index_symbol": "QQQ",
                    "volatility_class": "high",
                    "provider": "yfinance",
                    "qdii": True,
                    "strategy_plan": {
                        "monthly_budget_amount": 400,
                        "unit_amount": 100,
                        "month_end_fill": True,
                        "fill_last_trading_days": 5,
                    },
                    "funds": [
                        {
                            "code": "021778",
                            "name": "广发纳斯达克100F",
                            "enabled": True,
                            "strategy_enabled": True,
                            "strategy_priority": 1,
                        }
                    ],
                }
            }
        },
        strategy={},
        budget={},
        calendars={},
    )
