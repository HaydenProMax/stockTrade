from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from fund_signal.config import AppConfig
from fund_signal.retriever import KnowledgeHit, retrieve_markdown


MatchMap = dict[str, set[str]]


@dataclass(frozen=True)
class LatestRunContext:
    run_date: str
    mode: str
    signals: list[dict]
    allocations: list[dict]


def answer_local_question(config: AppConfig, question: str) -> str:
    matches = _match_assets_and_funds(config, question)
    archived_matches = _match_archived_funds(config, question)
    latest = _latest_run_context(config.root / "data" / "fund_signal.sqlite")
    preferred_paths = _preferred_fund_doc_paths(config.root, matches)
    knowledge_hits = retrieve_markdown(config.root, question, preferred_paths=preferred_paths)

    lines = [
        "# 本地策略回答",
        "",
        f"问题：{question}",
        "",
    ]

    if not matches and archived_matches:
        lines.extend(
            [
                "## 归档基金",
                "",
                "问题命中了已归档基金；它们不再作为当前长期持有清单的一部分，也不参与当前 `ask` 的基金资料检索。",
                "",
            ]
        )
        for fund_code, fund_name in archived_matches:
            lines.append(f"- {fund_code} {fund_name}")
        lines.append("")
        lines.extend(_latest_summary_lines(latest))
        return "\n".join(lines)

    if not matches:
        lines.extend(
            [
                "## 匹配结果",
                "",
                "没有从问题中识别到具体资产组或基金代码。你可以提到资产组名称、资产组 key 或基金代码，例如 `纳指100`、`nasdaq100`、`021778`。",
                "",
                "可用资产组：",
                "",
            ]
        )
        for asset_group, asset_config in config.assets.get("asset_groups", {}).items():
            if not _enabled_funds(asset_config):
                continue
            lines.append(f"- {asset_config.get('name', asset_group)} (`{asset_group}`)")
        lines.append("")
        lines.extend(_latest_summary_lines(latest))
        lines.extend(_knowledge_hit_lines(config.root, knowledge_hits))
        return "\n".join(lines)

    lines.extend(_latest_summary_lines(latest))
    for asset_group, fund_codes in matches.items():
        asset_config = config.assets["asset_groups"][asset_group]
        lines.extend(_asset_answer_lines(asset_group, asset_config, latest, fund_codes))

    lines.extend(
        [
            "## 判断边界",
            "",
            "- 这里基于本地配置和最近一次已保存运行结果，不替代实时行情重新计算。",
            "- 若刚刚只跑了 `--dry-run`，结果不会写入 SQLite，因此不会出现在这里。",
            "- 要刷新判断，请先运行 `python -m fund_signal.cli run --mode afternoon` 或 `--mode manual`。",
            "",
        ]
    )
    lines.extend(_knowledge_hit_lines(config.root, knowledge_hits))
    return "\n".join(lines)


def _match_assets_and_funds(config: AppConfig, question: str) -> MatchMap:
    normalized_question = question.lower()
    matches: MatchMap = {}
    for asset_group, asset_config in config.assets.get("asset_groups", {}).items():
        enabled_funds = _enabled_funds(asset_config)
        if not enabled_funds:
            continue
        asset_names = [
            asset_group,
            str(asset_config.get("name", "")),
            str(asset_config.get("index_symbol", "")),
        ]
        asset_matched = any(
            name and name.lower() in normalized_question
            for name in asset_names
        )
        fund_matches = set()
        for fund in enabled_funds:
            fund_names = [str(fund.get("code", "")), str(fund.get("name", ""))]
            if any(name and name.lower() in normalized_question for name in fund_names):
                fund_matches.add(str(fund.get("code", "")))
        if asset_matched or fund_matches:
            matches[asset_group] = fund_matches
    return matches


def _match_archived_funds(config: AppConfig, question: str) -> list[tuple[str, str]]:
    normalized_question = question.lower()
    matches: list[tuple[str, str]] = []
    for asset_config in config.assets.get("asset_groups", {}).values():
        for fund in asset_config.get("funds", []):
            if fund.get("enabled", True):
                continue
            fund_names = [str(fund.get("code", "")), str(fund.get("name", ""))]
            if any(name and name.lower() in normalized_question for name in fund_names):
                matches.append((str(fund.get("code", "")), str(fund.get("name", ""))))
    return matches


def _preferred_fund_doc_paths(root: Path, matches: MatchMap) -> set[Path]:
    return {
        root / "knowledge" / "external" / "fund_docs" / f"{fund_code}.md"
        for fund_codes in matches.values()
        for fund_code in fund_codes
    }


def _latest_run_context(db_path: Path) -> LatestRunContext | None:
    if not db_path.exists():
        return None
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT run_date, mode
            FROM runs
            WHERE status = 'success'
            ORDER BY run_date DESC, id DESC
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            return None

        run_date = str(row["run_date"])
        mode = str(row["mode"])
        signals = [
            dict(item)
            for item in connection.execute(
                """
                SELECT asset_group, source, data_date, drawdown, daily_change,
                       raw_units, final_units, trend_state, reason
                FROM signals
                WHERE run_date = ? AND mode = ?
                ORDER BY asset_group
                """,
                (run_date, mode),
            ).fetchall()
        ]
        allocations = [
            dict(item)
            for item in connection.execute(
                """
                SELECT asset_group, fund_code, fund_name, units, amount,
                       executed_amount, status, reason
                FROM allocations
                WHERE run_date = ? AND mode = ?
                ORDER BY asset_group, fund_code
                """,
                (run_date, mode),
            ).fetchall()
        ]
    return LatestRunContext(run_date=run_date, mode=mode, signals=signals, allocations=allocations)


def _latest_summary_lines(latest: LatestRunContext | None) -> list[str]:
    if latest is None:
        return [
            "## 最新运行结果",
            "",
            "未找到已保存的成功运行结果。当前只能解释配置规则，不能判断最近一次是否建议买入。",
            "",
        ]
    return [
        "## 最新运行结果",
        "",
        f"- 日期：{latest.run_date}",
        f"- 模式：{latest.mode}",
        f"- 信号数量：{len(latest.signals)}",
        f"- allocation 数量：{len(latest.allocations)}",
        "",
    ]


def _asset_answer_lines(
    asset_group: str,
    asset_config: dict,
    latest: LatestRunContext | None,
    matched_fund_codes: set[str],
) -> list[str]:
    lines = [
        f"## {asset_config.get('name', asset_group)} (`{asset_group}`)",
        "",
        f"- 市场：{asset_config.get('market', '未配置')}",
        f"- 指数/代理：{asset_config.get('index_symbol', '未配置')}",
        f"- 波动分类：{asset_config.get('volatility_class', '未配置')}",
        f"- 数据源：{asset_config.get('provider', '未配置')}",
        f"- QDII：{'是' if asset_config.get('qdii') else '否'}",
    ]

    strategy_plan = asset_config.get("strategy_plan")
    if strategy_plan:
        lines.append(
            "- 策略预算："
            f"月预算 {strategy_plan.get('monthly_budget_amount')} 元，"
            f"1U={strategy_plan.get('unit_amount')} 元"
        )
        if strategy_plan.get("month_end_fill"):
            lines.append(
                "- 月末补投：开启，最后 "
                f"{strategy_plan.get('fill_last_trading_days', 5)} 个中国交易日观察"
            )
    else:
        lines.append("- 策略预算：未配置策略型买入计划")

    fixed_plans = _fixed_plan_lines(asset_config)
    if fixed_plans:
        lines.append("- 固定计划：" + "；".join(fixed_plans))

    lines.append("")
    lines.extend(_fund_table_lines(asset_config))
    lines.append("")
    lines.extend(_latest_asset_signal_lines(asset_group, latest))
    lines.extend(_latest_asset_allocation_lines(asset_group, latest, matched_fund_codes))
    return lines


def _fixed_plan_lines(asset_config: dict) -> list[str]:
    plans: list[str] = []
    for fund in _enabled_funds(asset_config):
        for plan in fund.get("plans", []):
            plan_type = plan.get("type")
            amount = plan.get("amount")
            monthly = plan.get("monthly_budget_amount")
            plans.append(f"{fund.get('code')} {plan_type} {amount} 元/次，月预算 {monthly} 元")
    return plans


def _fund_table_lines(asset_config: dict) -> list[str]:
    funds = _enabled_funds(asset_config)
    if not funds:
        return ["基金：未配置"]
    lines = [
        "| 基金代码 | 基金名称 | 用途 | 优先级 | 日限额 |",
        "|---|---|---|---:|---:|",
    ]
    for fund in funds:
        purpose = "策略买入" if fund.get("strategy_enabled") else "固定/观察"
        lines.append(
            "| "
            f"{fund.get('code', '')} | "
            f"{fund.get('name', '')} | "
            f"{purpose} | "
            f"{fund.get('strategy_priority', '')} | "
            f"{fund.get('daily_limit_amount', '')} |"
        )
    return lines


def _enabled_funds(asset_config: dict) -> list[dict]:
    return [fund for fund in asset_config.get("funds", []) if fund.get("enabled", True)]


def _latest_asset_signal_lines(asset_group: str, latest: LatestRunContext | None) -> list[str]:
    lines = ["### 最近信号", ""]
    if latest is None:
        return [*lines, "无已保存信号。", ""]

    signal = next((item for item in latest.signals if item["asset_group"] == asset_group), None)
    if signal is None:
        return [*lines, "最近一次运行没有该资产组信号。", ""]

    lines.extend(
        [
            f"- 数据日期：{signal['data_date']}",
            f"- 回撤：{float(signal['drawdown']):.2%}",
            f"- 当日涨跌：{float(signal['daily_change']):.2%}",
            f"- 原始 U 数：{float(signal['raw_units']):g}",
            f"- 最终 U 数：{float(signal['final_units']):g}",
            f"- 趋势状态：{signal['trend_state']}",
            "",
        ]
    )
    return lines


def _latest_asset_allocation_lines(
    asset_group: str,
    latest: LatestRunContext | None,
    matched_fund_codes: set[str],
) -> list[str]:
    lines = ["### 最近 allocation", ""]
    if latest is None:
        return [*lines, "无已保存 allocation。", ""]

    allocations = [item for item in latest.allocations if item["asset_group"] == asset_group]
    if matched_fund_codes:
        allocations = [item for item in allocations if item["fund_code"] in matched_fund_codes]
    if not allocations:
        if matched_fund_codes:
            funds = ", ".join(sorted(matched_fund_codes))
            return [*lines, f"最近一次运行没有匹配基金 {funds} 的 allocation。", ""]
        return [*lines, "最近一次运行没有该资产组 allocation。", ""]

    executable = [
        item for item in allocations
        if float(item["amount"] or 0) > 0 and "assumed_executed" in str(item["status"])
    ]
    scope = "匹配基金" if matched_fund_codes else "该资产组"
    if executable:
        total = sum(float(item["amount"] or 0) for item in executable)
        lines.append(f"结论：最近一次已保存运行中，{scope}有默认执行金额 {total:g} 元。")
    else:
        lines.append(f"结论：最近一次已保存运行中，{scope}没有默认执行买入金额。")
    lines.append("")
    lines.append("| 基金代码 | 金额 | 状态 | 原因 |")
    lines.append("|---|---:|---|---|")
    for item in allocations:
        lines.append(
            "| "
            f"{item['fund_code']} | "
            f"{float(item['amount'] or 0):g} | "
            f"{item['status']} | "
            f"{item['reason']} |"
        )
    lines.append("")
    return lines


def _knowledge_hit_lines(root: Path, hits: list[KnowledgeHit]) -> list[str]:
    lines = ["## 相关知识片段", ""]
    if not hits:
        return [*lines, "没有检索到匹配的本地知识片段。", ""]

    for hit in hits:
        try:
            display_path = hit.path.relative_to(root)
        except ValueError:
            display_path = hit.path
        lines.extend(
            [
                f"### {hit.heading}",
                "",
                f"来源：`{display_path}`",
                "",
                hit.text,
                "",
            ]
        )
    return lines
