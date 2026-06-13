from __future__ import annotations

from pathlib import Path

from fund_signal.retriever import (
    format_knowledge_search,
    format_knowledge_sources,
    list_knowledge_sources,
    retrieve_markdown,
)


def test_retrieve_markdown_returns_relevant_knowledge_hits(tmp_path):
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    (knowledge_dir / "personal_strategy.md").write_text(
        "# 个人策略\n\n## 纳指100\n\n021778 月末补投，最后 5 个中国交易日观察。",
        encoding="utf-8",
    )
    (knowledge_dir / "other.md").write_text(
        "# 其他\n\n红利低波固定底仓。",
        encoding="utf-8",
    )

    hits = retrieve_markdown(tmp_path, "021778 月末补投")

    assert hits
    assert hits[0].path.name == "personal_strategy.md"
    assert hits[0].heading == "纳指100"
    assert "021778 月末补投" in hits[0].text


def test_retrieve_markdown_includes_strategy_records(tmp_path):
    records_dir = tmp_path / "strategy_records"
    records_dir.mkdir()
    (records_dir / "strategy.md").write_text(
        "# 策略记录\n\n全球科技互联 006373 A 类优先。",
        encoding="utf-8",
    )

    hits = retrieve_markdown(tmp_path, "006373 A 类优先")

    assert hits
    assert hits[0].path.name == "strategy.md"


def test_retrieve_markdown_prioritizes_current_strategy_record(tmp_path):
    records_dir = tmp_path / "strategy_records"
    records_dir.mkdir()
    (records_dir / "strategy_20260530_old.md").write_text(
        "# 旧策略\n\n纳指100 月预算 400 元。",
        encoding="utf-8",
    )
    (records_dir / "strategy_20260701_current_monthly_plan.md").write_text(
        "# 当前策略\n\n纳指100 月预算 1260 元。",
        encoding="utf-8",
    )

    hits = retrieve_markdown(tmp_path, "纳指100 月预算")

    assert hits[0].path.name == "strategy_20260701_current_monthly_plan.md"


def test_retrieve_markdown_excludes_archived_knowledge(tmp_path):
    active_dir = tmp_path / "knowledge" / "external" / "fund_docs"
    archive_dir = tmp_path / "knowledge" / "external" / "archive" / "fund_docs" / "2026-06-13"
    active_dir.mkdir(parents=True)
    archive_dir.mkdir(parents=True)
    (active_dir / "270042.md").write_text("# 270042\n\n长期持有。", encoding="utf-8")
    (archive_dir / "021778.md").write_text("# 021778\n\n归档基金。", encoding="utf-8")

    hits = retrieve_markdown(tmp_path, "归档基金")

    assert hits == []


def test_list_knowledge_sources_reads_titles_and_sizes(tmp_path):
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    (knowledge_dir / "source.md").write_text("# SEC ETF Guide\n\nETF fees.", encoding="utf-8")

    sources = list_knowledge_sources(tmp_path)

    assert len(sources) == 1
    assert sources[0].title == "SEC ETF Guide"
    assert sources[0].chars > 0


def test_format_knowledge_helpers(tmp_path):
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    (knowledge_dir / "source.md").write_text(
        "# SEC ETF Guide\n\n## ETF fees\n\nExpense ratio and tracking risk.",
        encoding="utf-8",
    )

    source_output = format_knowledge_sources(tmp_path)
    search_output = format_knowledge_search(tmp_path, "ETF fees")

    source_display_path = str(Path("knowledge") / "source.md")
    assert f"| {source_display_path} | SEC ETF Guide |" in source_output
    assert "# 本地知识检索" in search_output
    assert f"来源：`{source_display_path}`" in search_output
    assert "Expense ratio and tracking risk" in search_output


def test_retrieve_markdown_boosts_preferred_paths(tmp_path):
    fund_docs = tmp_path / "knowledge" / "external" / "fund_docs"
    fund_docs.mkdir(parents=True)
    preferred = fund_docs / "021778.md"
    preferred.write_text("# 021778\n\n费用说明。", encoding="utf-8")
    (tmp_path / "knowledge" / "other.md").write_text(
        "# Other\n\n021778 021778 021778 普通片段。",
        encoding="utf-8",
    )

    hits = retrieve_markdown(tmp_path, "021778", preferred_paths={preferred})

    assert hits[0].path == preferred
