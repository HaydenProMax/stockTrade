from __future__ import annotations

from fund_signal.config import AppConfig
from fund_signal.knowledge import (
    FundDocError,
    audit_fund_docs,
    build_personal_strategy_markdown,
    import_external_markdown,
    import_fund_doc_section,
    write_fund_doc_templates,
    write_personal_strategy_markdown,
)


def test_build_personal_strategy_markdown_summarizes_config_and_records(tmp_path):
    records_dir = tmp_path / "strategy_records"
    records_dir.mkdir()
    (records_dir / "strategy_20260601.md").write_text(
        "# 策略确认记录\n\n006373 A 类优先。",
        encoding="utf-8",
    )
    config = _config(tmp_path)

    markdown = build_personal_strategy_markdown(config)

    assert "# 个人指数基金策略知识层" in markdown
    assert "全组合月投入硬上限：5500 元" in markdown
    assert "纳指100 (`nasdaq100`)" in markdown
    assert "021778" in markdown
    assert "月末补投：开启" in markdown
    assert "`strategy_20260601.md`：策略确认记录" in markdown
    assert "是否生成买入建议，应以程序实时计算结果和 SQLite 记录为准" in markdown


def test_write_personal_strategy_markdown_uses_default_path(tmp_path):
    output_path = write_personal_strategy_markdown(_config(tmp_path))

    assert output_path == tmp_path / "knowledge" / "personal_strategy.md"
    assert output_path.read_text(encoding="utf-8").startswith("# 个人指数基金策略知识层")


def test_write_fund_doc_templates_creates_templates_without_overwriting(tmp_path):
    output_dir = tmp_path / "knowledge" / "external" / "fund_docs"
    output_dir.mkdir(parents=True)
    existing = output_dir / "021778.md"
    existing.write_text("# Existing\n", encoding="utf-8")

    written = write_fund_doc_templates(_config(tmp_path), output_dir)

    assert written == []
    assert existing.read_text(encoding="utf-8") == "# Existing\n"

    existing.unlink()
    written = write_fund_doc_templates(_config(tmp_path), output_dir)

    assert written == [output_dir / "021778.md"]
    text = written[0].read_text(encoding="utf-8")
    assert "# 021778 广发纳斯达克100F" in text
    assert "## 跟踪指数" in text
    assert "## 持仓信息" in text
    assert "## 风险提示" in text


def test_fund_doc_templates_skip_disabled_funds(tmp_path):
    config = _config(tmp_path)
    config.assets["asset_groups"]["nasdaq100"]["funds"][0]["enabled"] = False

    written = write_fund_doc_templates(config)
    report = audit_fund_docs(config)

    assert written == []
    assert "未从资产配置中发现基金" in report


def test_audit_fund_docs_reports_missing_and_incomplete_docs(tmp_path):
    report = audit_fund_docs(_config(tmp_path))

    assert "缺失文件：1" in report
    assert "| 021778 | 广发纳斯达克100F | 缺文件 | 0 | 缺文件 |" in report

    output_dir = tmp_path / "knowledge" / "external" / "fund_docs"
    write_fund_doc_templates(_config(tmp_path), output_dir)

    report = audit_fund_docs(_config(tmp_path), output_dir)

    assert "缺失文件：0" in report
    assert "缺来源" in report
    assert "含待补充" in report


def test_audit_fund_docs_accepts_completed_doc(tmp_path):
    output_dir = tmp_path / "knowledge" / "external" / "fund_docs"
    output_dir.mkdir(parents=True)
    (output_dir / "021778.md").write_text(
        "\n".join(
            [
                "# 021778 广发纳斯达克100F",
                "",
                "来源：https://example.com/fund",
                "资料日期：2026-06-01",
                "下载日期：2026-06-03",
                "",
                "## 基金事实",
                "已补充。",
                "## 跟踪指数",
                "已补充。",
                "## 持仓信息",
                "已补充。",
                "## 费用",
                "已补充。",
                "## 申购限制",
                "已补充。",
                "## 分红与税务",
                "已补充。",
                "## 风险提示",
                "已补充。",
            ]
        ),
        encoding="utf-8",
    )

    report = audit_fund_docs(_config(tmp_path), output_dir)

    assert "仍需补充：0" in report
    assert "| 021778 | 广发纳斯达克100F | 完成 | 0 | - |" in report


def test_audit_fund_docs_strict_rejects_third_party_and_vague_wording(tmp_path):
    output_dir = tmp_path / "knowledge" / "external" / "fund_docs"
    output_dir.mkdir(parents=True)
    (output_dir / "021778.md").write_text(
        "\n".join(
            [
                "# 021778 广发纳斯达克100F",
                "",
                "来源：https://fund.eastmoney.com/021778.html",
                "资料日期：2026-06-01",
                "下载日期：2026-06-03",
                "",
                "## 基金事实",
                "产品资料概要显示基金事实。",
                "## 跟踪指数",
                "已补充。",
                "## 持仓信息",
                "具体费率与持仓以基金公司最新招募说明书为准。",
                "## 费用",
                "已补充。",
                "## 申购限制",
                "已补充。",
                "## 分红与税务",
                "已补充。",
                "## 风险提示",
                "已补充。",
            ]
        ),
        encoding="utf-8",
    )

    normal_report = audit_fund_docs(_config(tmp_path), output_dir)
    strict_report = audit_fund_docs(_config(tmp_path), output_dir, strict=True)

    assert "仍需补充：0" in normal_report
    assert "含第三方来源:eastmoney.com" in strict_report
    assert "含泛泛口径:以基金公司最新招募说明书" in strict_report


def test_audit_fund_docs_strict_rejects_cross_share_class_reference(tmp_path):
    output_dir = tmp_path / "knowledge" / "external" / "fund_docs"
    output_dir.mkdir(parents=True)
    (output_dir / "021778.md").write_text(
        "\n".join(
            [
                "# 021778 广发纳斯达克100F",
                "",
                "来源：https://www.gffunds.com.cn/jjgg/flwj/example.pdf",
                "资料日期：2026-06-01 产品资料概要",
                "下载日期：2026-06-03",
                "",
                "## 基金事实",
                "产品资料概要显示基金事实。",
                "## 跟踪指数",
                "已补充。",
                "## 持仓信息",
                "已补充。",
                "## 费用",
                "参考同基金其他份额文件，对应份额最新文件待核。",
                "## 申购限制",
                "已补充。",
                "## 分红与税务",
                "已补充。",
                "## 风险提示",
                "已补充。",
            ]
        ),
        encoding="utf-8",
    )

    strict_report = audit_fund_docs(_config(tmp_path), output_dir, strict=True)

    assert "含泛泛口径:参考同基金" in strict_report
    assert "含泛泛口径:对应份额最新" in strict_report


def test_import_fund_doc_section_replaces_section_and_metadata(tmp_path):
    output_dir = tmp_path / "knowledge" / "external" / "fund_docs"
    write_fund_doc_templates(_config(tmp_path), output_dir)
    source = tmp_path / "fees.md"
    source.write_text("管理费：0.50%\n托管费：0.10%", encoding="utf-8")

    path = import_fund_doc_section(
        _config(tmp_path),
        "021778",
        "费用",
        source,
        source_url="https://example.com/021778",
        material_date="2026-06-01",
        download_date="2026-06-03",
        docs_dir=output_dir,
    )

    text = path.read_text(encoding="utf-8")
    assert "来源：https://example.com/021778" in text
    assert "资料日期：2026-06-01" in text
    assert "下载日期：2026-06-03" in text
    assert "## 费用\n\n管理费：0.50%\n托管费：0.10%" in text
    assert "## 申购限制" in text
    assert "待补充管理费" not in text


def test_import_fund_doc_section_rejects_unknown_section(tmp_path):
    output_dir = tmp_path / "knowledge" / "external" / "fund_docs"
    write_fund_doc_templates(_config(tmp_path), output_dir)
    source = tmp_path / "unknown.md"
    source.write_text("内容", encoding="utf-8")

    try:
        import_fund_doc_section(
            _config(tmp_path),
            "021778",
            "不存在",
            source,
            docs_dir=output_dir,
        )
    except FundDocError as exc:
        assert "Unsupported section" in str(exc)
    else:
        raise AssertionError("Expected FundDocError")


def test_import_external_markdown_writes_normalized_document(tmp_path):
    source = tmp_path / "sec.md"
    source.write_text("# ETF Fees\n\nExpense ratios matter.", encoding="utf-8")

    path = import_external_markdown(
        _config(tmp_path),
        "SEC FINRA",
        "ETF Fees",
        source,
        source_url="https://example.com/sec",
        material_date="2026-06-01",
        download_date="2026-06-03",
    )

    assert path == tmp_path / "knowledge" / "external" / "sec-finra" / "etf-fees.md"
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# ETF Fees\n")
    assert "类别：sec-finra" in text
    assert "来源：https://example.com/sec" in text
    assert "资料日期：2026-06-01" in text
    assert "下载日期：2026-06-03" in text
    assert text.count("# ETF Fees") == 1
    assert "Expense ratios matter." in text


def test_import_external_markdown_refuses_overwrite_without_flag(tmp_path):
    source = tmp_path / "irs.md"
    source.write_text("Capital gains.", encoding="utf-8")
    import_external_markdown(_config(tmp_path), "irs", "pub-550", source)

    try:
        import_external_markdown(_config(tmp_path), "irs", "pub-550", source)
    except FundDocError as exc:
        assert "Target already exists" in str(exc)
    else:
        raise AssertionError("Expected FundDocError")

    path = import_external_markdown(
        _config(tmp_path),
        "irs",
        "pub-550",
        source,
        title="IRS Pub 550",
        overwrite=True,
    )

    assert path.read_text(encoding="utf-8").startswith("# IRS Pub 550")


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
                    "tech_growth": True,
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
        strategy={
            "drawdown_window_days": 250,
            "moving_average_days": [60, 120, 250],
            "volatility_classes": {
                "high": {
                    "bands": [
                        {"max_drawdown": -0.10, "units": 0},
                        {"max_drawdown": -0.15, "units": 1},
                        {"max_drawdown": None, "units": 3},
                    ]
                }
            },
            "trend_filter": {
                "above_ma_60_multiplier": 0,
                "below_ma_60_above_ma_120_multiplier": 0.5,
                "below_ma_120_multiplier": 1,
            },
            "drawdown_duration_adjustment": {
                "enabled": True,
                "early_multiplier": 0.5,
                "normal_multiplier": 1,
                "late_multiplier": 1.2,
            },
            "active_qdii": {"fund_nav_drawdown_confirm": -0.08},
        },
        budget={
            "portfolio_monthly_hard_limit_amount": 5500,
            "assume_recommended_allocations_executed": True,
            "tech_growth": {
                "asset_groups": ["nasdaq100"],
                "monthly_observe_amount": 2500,
                "monthly_warning_amount": 3000,
            },
        },
        calendars={},
    )
