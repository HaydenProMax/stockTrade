from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from fund_signal.config import AppConfig


REQUIRED_FUND_DOC_SECTIONS = [
    "基金事实",
    "跟踪指数",
    "持仓信息",
    "费用",
    "申购限制",
    "分红与税务",
    "风险提示",
]

DISALLOWED_STRICT_SOURCE_DOMAINS = [
    "eastmoney.com",
    "fund.eastmoney.com",
    "tiantianfunds.com",
    "xueqiu.com",
    "licai.com",
]

VAGUE_STRICT_PHRASES = [
    "以基金公司最新招募说明书",
    "以最新招募说明书",
    "以最新产品资料概要",
    "以销售渠道",
    "以官方文件为准",
    "以基金公司文件为准",
    "待官方确认",
    "具体费率与持仓",
    "参考同基金",
    "对应份额最新",
    "应以对应份额",
]

STRICT_EVIDENCE_TERMS = [
    "产品资料概要",
    "招募说明书",
    "季度报告",
    "年度报告",
    "半年报告",
    "公告",
]


class FundDocError(ValueError):
    pass


def build_personal_strategy_markdown(config: AppConfig) -> str:
    lines: list[str] = [
        "# 个人指数基金策略知识层",
        "",
        f"生成时间：{datetime.now().isoformat(timespec='seconds')}",
        "",
        "## 1. 组合约束",
        "",
    ]
    lines.extend(_budget_lines(config.budget))
    lines.extend(
        [
            "",
            "## 2. 策略参数",
            "",
        ]
    )
    lines.extend(_strategy_lines(config.strategy))
    lines.extend(
        [
            "",
            "## 3. 资产组与基金计划",
            "",
        ]
    )
    for asset_group, asset_config in config.assets.get("asset_groups", {}).items():
        if not _enabled_funds(asset_config):
            continue
        lines.extend(_asset_group_lines(asset_group, asset_config))
        lines.append("")

    record_lines = _strategy_record_lines(config.root / "strategy_records")
    if record_lines:
        lines.extend(
            [
                "## 4. 策略记录索引",
                "",
                *record_lines,
                "",
            ]
        )

    lines.extend(
        [
            "## 5. 使用边界",
            "",
            "- 本文件来自本地 YAML 配置和策略记录，只作为个人策略解释层。",
            "- 是否生成买入建议，应以程序实时计算结果和 SQLite 记录为准。",
            "- 外部基金文件、监管资料、税务资料应作为独立知识源补充。",
            "",
        ]
    )
    return "\n".join(lines)


def write_personal_strategy_markdown(config: AppConfig, output_path: Path | None = None) -> Path:
    target = output_path or config.root / "knowledge" / "personal_strategy.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(build_personal_strategy_markdown(config), encoding="utf-8")
    return target


def write_fund_doc_templates(config: AppConfig, output_dir: Path | None = None) -> list[Path]:
    target_dir = output_dir or config.root / "knowledge" / "external" / "fund_docs"
    target_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for asset_group, asset_config in config.assets.get("asset_groups", {}).items():
        for fund in asset_config.get("funds", []):
            if not fund.get("enabled", True):
                continue
            code = str(fund.get("code", "")).strip()
            if not code:
                continue
            path = target_dir / f"{code}.md"
            if path.exists():
                continue
            path.write_text(
                _fund_doc_template(asset_group, asset_config, fund),
                encoding="utf-8",
            )
            written.append(path)
    return written


def audit_fund_docs(config: AppConfig, docs_dir: Path | None = None, strict: bool = False) -> str:
    target_dir = docs_dir or config.root / "knowledge" / "external" / "fund_docs"
    expected = _expected_fund_docs(config)
    lines = [
        "# 基金文件体检",
        "",
        f"目录：`{target_dir}`",
        "",
    ]

    if not expected:
        lines.extend(["未从资产配置中发现基金。", ""])
        return "\n".join(lines)

    rows: list[tuple[str, str, str, int, str]] = []
    missing_files: list[str] = []
    incomplete_count = 0
    for code, name in expected:
        path = target_dir / f"{code}.md"
        if not path.exists():
            missing_files.append(code)
            rows.append((code, name, "缺文件", 0, "缺文件"))
            incomplete_count += 1
            continue

        text = path.read_text(encoding="utf-8")
        issues = _fund_doc_issues(text)
        if strict:
            issues.extend(_strict_fund_doc_issues(text))
        if issues:
            incomplete_count += 1
        status = "需补充" if issues else "完成"
        rows.append((code, name, status, text.count("待补充"), "；".join(issues) or "-"))

    lines.extend(
        [
            f"- 应有基金文件：{len(expected)}",
            f"- 缺失文件：{len(missing_files)}",
            f"- 仍需补充：{incomplete_count}",
            f"- 严谨模式：{'开启' if strict else '关闭'}",
            "",
            "| 基金代码 | 基金名称 | 状态 | 待补充数 | 问题 |",
            "|---|---|---|---:|---|",
        ]
    )
    for code, name, status, todo_count, issues in rows:
        lines.append(f"| {code} | {name} | {status} | {todo_count} | {issues} |")
    lines.append("")
    return "\n".join(lines)


def import_fund_doc_section(
    config: AppConfig,
    fund_code: str,
    section: str,
    source_path: Path,
    *,
    source_url: str | None = None,
    material_date: str | None = None,
    download_date: str | None = None,
    docs_dir: Path | None = None,
) -> Path:
    target_dir = docs_dir or config.root / "knowledge" / "external" / "fund_docs"
    target_path = target_dir / f"{fund_code}.md"
    if not target_path.exists():
        raise FundDocError(f"Missing fund doc: {target_path}")
    if not source_path.exists():
        raise FundDocError(f"Missing source file: {source_path}")
    if section not in REQUIRED_FUND_DOC_SECTIONS:
        allowed = ", ".join(REQUIRED_FUND_DOC_SECTIONS)
        raise FundDocError(f"Unsupported section '{section}'. Allowed sections: {allowed}")

    fund_doc = target_path.read_text(encoding="utf-8")
    imported_text = source_path.read_text(encoding="utf-8").strip()
    if not imported_text:
        raise FundDocError(f"Source file is empty: {source_path}")

    fund_doc = _set_metadata(fund_doc, "来源", source_url)
    fund_doc = _set_metadata(fund_doc, "资料日期", material_date)
    fund_doc = _set_metadata(fund_doc, "下载日期", download_date)
    fund_doc = _replace_section(fund_doc, section, imported_text)
    target_path.write_text(fund_doc, encoding="utf-8")
    return target_path


def import_external_markdown(
    config: AppConfig,
    category: str,
    slug: str,
    source_path: Path,
    *,
    title: str | None = None,
    source_url: str | None = None,
    material_date: str | None = None,
    download_date: str | None = None,
    output_root: Path | None = None,
    overwrite: bool = False,
) -> Path:
    if not source_path.exists():
        raise FundDocError(f"Missing source file: {source_path}")

    normalized_category = _safe_path_part(category)
    normalized_slug = _safe_path_part(slug)
    if not normalized_category or not normalized_slug:
        raise FundDocError("Category and slug must contain letters, numbers, dashes, or underscores.")

    target_root = output_root or config.root / "knowledge" / "external"
    target_dir = target_root / normalized_category
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{normalized_slug}.md"
    if target_path.exists() and not overwrite:
        raise FundDocError(f"Target already exists: {target_path}. Use --overwrite to replace it.")

    body = source_path.read_text(encoding="utf-8").strip()
    if not body:
        raise FundDocError(f"Source file is empty: {source_path}")

    document_title = title or _first_markdown_heading(body) or normalized_slug
    target_path.write_text(
        _external_markdown_document(
            document_title,
            category=normalized_category,
            source_url=source_url,
            material_date=material_date,
            download_date=download_date,
            body=body,
        ),
        encoding="utf-8",
    )
    return target_path


def _budget_lines(budget: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    hard_limit = budget.get("portfolio_monthly_hard_limit_amount")
    if hard_limit is not None:
        lines.append(f"- 全组合月投入硬上限：{hard_limit} 元")

    if budget.get("assume_recommended_allocations_executed") is not None:
        value = "是" if budget.get("assume_recommended_allocations_executed") else "否"
        lines.append(f"- 默认将推荐 allocation 计入已执行预算：{value}")

    tech_growth = budget.get("tech_growth", {})
    if tech_growth:
        groups = ", ".join(tech_growth.get("asset_groups", []))
        lines.append(f"- 科技成长资产组：{groups}")
        if tech_growth.get("monthly_observe_amount") is not None:
            lines.append(f"- 科技成长月观察阈值：{tech_growth['monthly_observe_amount']} 元")
        if tech_growth.get("monthly_warning_amount") is not None:
            lines.append(f"- 科技成长月警告阈值：{tech_growth['monthly_warning_amount']} 元")

    sell_rules = budget.get("sell_rules", {})
    if sell_rules:
        enabled = "开启" if sell_rules.get("enabled") else "关闭"
        lines.append(f"- 卖出规则：{enabled}")
        excluded = ", ".join(sell_rules.get("excluded_asset_groups", []))
        if excluded:
            lines.append(f"- 卖出规则排除资产组：{excluded}")

    return lines or ["- 未配置组合预算约束。"]


def _expected_fund_docs(config: AppConfig) -> list[tuple[str, str]]:
    funds: list[tuple[str, str]] = []
    for asset_config in config.assets.get("asset_groups", {}).values():
        for fund in asset_config.get("funds", []):
            if not fund.get("enabled", True):
                continue
            code = str(fund.get("code", "")).strip()
            name = str(fund.get("name", "")).strip()
            if code:
                funds.append((code, name))
    return funds


def _fund_doc_issues(text: str) -> list[str]:
    issues: list[str] = []
    for label in ["来源", "资料日期", "下载日期"]:
        if _metadata_is_blank(text, label):
            issues.append(f"缺{label}")

    for section in REQUIRED_FUND_DOC_SECTIONS:
        if f"## {section}" not in text:
            issues.append(f"缺章节:{section}")

    if "待补充" in text:
        issues.append("含待补充")
    return issues


def _strict_fund_doc_issues(text: str) -> list[str]:
    issues: list[str] = []
    lower_text = text.lower()

    for domain in DISALLOWED_STRICT_SOURCE_DOMAINS:
        if domain in lower_text:
            issues.append(f"含第三方来源:{domain}")

    if not any(term in text for term in STRICT_EVIDENCE_TERMS):
        issues.append("缺官方披露文件证据")

    for phrase in VAGUE_STRICT_PHRASES:
        if phrase in text:
            issues.append(f"含泛泛口径:{phrase}")

    return issues


def _metadata_is_blank(text: str, label: str) -> bool:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(f"{label}：") or stripped.startswith(f"{label}:"):
            _, _, value = stripped.partition("：")
            if not value and ":" in stripped:
                _, _, value = stripped.partition(":")
            return not value.strip()
    return True


def _set_metadata(text: str, label: str, value: str | None) -> str:
    if not value:
        return text

    lines = text.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(f"{label}：") or stripped.startswith(f"{label}:"):
            lines[index] = f"{label}：{value}"
            return "\n".join(lines) + ("\n" if text.endswith("\n") else "")

    insert_at = 1 if lines else 0
    lines.insert(insert_at, f"{label}：{value}")
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def _replace_section(text: str, section: str, replacement: str) -> str:
    heading = f"## {section}"
    lines = text.splitlines()
    start = next((index for index, line in enumerate(lines) if line.strip() == heading), None)
    if start is None:
        raise FundDocError(f"Missing section: {section}")

    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break

    replacement_lines = [heading, "", *replacement.splitlines()]
    if end < len(lines):
        replacement_lines.append("")
    new_lines = [*lines[:start], *replacement_lines, *lines[end:]]
    return "\n".join(new_lines).rstrip() + "\n"


def _external_markdown_document(
    title: str,
    *,
    category: str,
    source_url: str | None,
    material_date: str | None,
    download_date: str | None,
    body: str,
) -> str:
    body_without_title = _strip_duplicate_title(body, title)
    return "\n".join(
        [
            f"# {title}",
            "",
            f"类别：{category}",
            f"来源：{source_url or ''}",
            f"资料日期：{material_date or ''}",
            f"下载日期：{download_date or ''}",
            "",
            body_without_title,
            "",
        ]
    )


def _safe_path_part(value: str) -> str:
    allowed = []
    for char in value.strip().lower().replace(" ", "-"):
        if char.isalnum() or char in {"-", "_"}:
            allowed.append(char)
    return "".join(allowed).strip("-_")


def _first_markdown_heading(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return None


def _strip_duplicate_title(body: str, title: str) -> str:
    lines = body.splitlines()
    if lines and lines[0].strip().lstrip("#").strip() == title:
        return "\n".join(lines[1:]).strip()
    return body


def _fund_doc_template(asset_group: str, asset_config: dict[str, Any], fund: dict[str, Any]) -> str:
    code = fund.get("code", "")
    name = fund.get("name", "")
    asset_name = asset_config.get("name", asset_group)
    index_symbol = asset_config.get("index_symbol", "")
    return "\n".join(
        [
            f"# {code} {name}",
            "",
            "来源：",
            "资料日期：",
            "下载日期：",
            "",
            "## 基金事实",
            "",
            f"- 基金代码：{code}",
            f"- 基金名称：{name}",
            f"- 所属资产组：{asset_name} (`{asset_group}`)",
            f"- 市场：{asset_config.get('market', '未配置')}",
            f"- 跟踪/代理指数：{index_symbol or '未配置'}",
            f"- QDII：{'是' if asset_config.get('qdii') else '否'}",
            f"- 策略优先级：{fund.get('strategy_priority', '未配置')}",
            f"- 日限额：{fund.get('daily_limit_amount', '未配置')}",
            "",
            "## 跟踪指数",
            "",
            "待补充官方说明。",
            "",
            "## 持仓信息",
            "",
            "待补充基金资产组合、前十大持仓、底层穿透持仓或目标 ETF 持仓说明。",
            "",
            "## 费用",
            "",
            "待补充管理费、托管费、销售服务费、申购赎回费等信息。",
            "",
            "## 申购限制",
            "",
            "待补充申购状态、限购金额、暂停申购说明。",
            "",
            "## 分红与税务",
            "",
            "待补充分红政策、历史分红、税务注意事项。",
            "",
            "## 风险提示",
            "",
            "待补充基金官方风险披露。",
            "",
        ]
    )


def _strategy_lines(strategy: dict[str, Any]) -> list[str]:
    lines = [
        f"- 回撤观察窗口：{strategy.get('drawdown_window_days')} 天",
        f"- 均线观察：{', '.join(str(day) for day in strategy.get('moving_average_days', []))} 天",
    ]
    trend = strategy.get("trend_filter", {})
    if trend:
        lines.extend(
            [
                f"- 站上 60 日均线：{trend.get('above_ma_60_multiplier')} 倍策略仓位",
                (
                    "- 跌破 60 日但站上 120 日均线："
                    f"{trend.get('below_ma_60_above_ma_120_multiplier')} 倍策略仓位"
                ),
                f"- 跌破 120 日均线：{trend.get('below_ma_120_multiplier')} 倍策略仓位",
            ]
        )

    volatility_classes = strategy.get("volatility_classes", {})
    for class_name, class_config in volatility_classes.items():
        band_text = []
        for band in class_config.get("bands", []):
            threshold = band.get("max_drawdown")
            threshold_text = "更深回撤" if threshold is None else f"{float(threshold):.0%}"
            band_text.append(f"{threshold_text} -> {band.get('units')}U")
        if band_text:
            lines.append(f"- {class_name} 波动资产回撤分层：{'; '.join(band_text)}")

    duration = strategy.get("drawdown_duration_adjustment", {})
    if duration.get("enabled"):
        lines.append(
            "- 回撤持续时间修正："
            f"早期 {duration.get('early_multiplier')} 倍，"
            f"常规 {duration.get('normal_multiplier')} 倍，"
            f"后期 {duration.get('late_multiplier')} 倍"
        )

    active_qdii = strategy.get("active_qdii", {})
    if active_qdii:
        lines.append(
            "- 主动 QDII 净值确认阈值："
            f"{float(active_qdii.get('fund_nav_drawdown_confirm', 0)):.0%}"
        )
    return lines


def _asset_group_lines(asset_group: str, asset_config: dict[str, Any]) -> list[str]:
    lines = [
        f"### {asset_config.get('name', asset_group)} (`{asset_group}`)",
        "",
        f"- 市场：{asset_config.get('market', '未配置')}",
        f"- 跟踪/代理指数：{asset_config.get('index_symbol', '未配置')}",
        f"- 波动分类：{asset_config.get('volatility_class', '未配置')}",
        f"- 数据源：{asset_config.get('provider', '未配置')}",
        f"- QDII：{'是' if asset_config.get('qdii') else '否'}",
        f"- 科技成长：{'是' if asset_config.get('tech_growth') else '否'}",
    ]

    proxy_weights = asset_config.get("proxy_weights", {})
    if proxy_weights:
        weights = ", ".join(f"{key}={value}" for key, value in proxy_weights.items())
        lines.append(f"- 代理权重：{weights}")

    strategy_plan = asset_config.get("strategy_plan")
    if strategy_plan:
        lines.append(
            "- 策略计划："
            f"月预算 {strategy_plan.get('monthly_budget_amount')} 元，"
            f"1U={strategy_plan.get('unit_amount')} 元"
        )
        if strategy_plan.get("month_end_fill"):
            lines.append(
                "- 月末补投：开启，窗口为最后 "
                f"{strategy_plan.get('fill_last_trading_days', 5)} 个中国交易日"
            )

    funds = _enabled_funds(asset_config)
    if not funds:
        lines.append("- 基金：未配置")
        return lines

    lines.append("")
    lines.append("| 基金代码 | 基金名称 | 启用 | 计划 | 策略优先级 | 日限额 |")
    lines.append("|---|---|---:|---|---:|---:|")
    for fund in funds:
        plans = _plan_text(fund.get("plans", []))
        priority = fund.get("strategy_priority", "")
        daily_limit = fund.get("daily_limit_amount", "")
        lines.append(
            "| "
            f"{fund.get('code', '')} | "
            f"{fund.get('name', '')} | "
            f"{'是' if fund.get('enabled', True) else '否'} | "
            f"{plans} | "
            f"{priority} | "
            f"{daily_limit} |"
        )
    return lines


def _plan_text(plans: list[dict[str, Any]]) -> str:
    if not plans:
        return "策略买入"
    parts = []
    for plan in plans:
        plan_type = plan.get("type", "unknown")
        amount = plan.get("amount")
        monthly = plan.get("monthly_budget_amount")
        if monthly is not None:
            parts.append(f"{plan_type}: {amount} 元/次，月预算 {monthly} 元")
        else:
            parts.append(f"{plan_type}: {amount} 元/次")
    return "; ".join(parts)


def _enabled_funds(asset_config: dict[str, Any]) -> list[dict[str, Any]]:
    return [fund for fund in asset_config.get("funds", []) if fund.get("enabled", True)]


def _strategy_record_lines(records_dir: Path) -> list[str]:
    if not records_dir.exists():
        return []

    lines: list[str] = []
    for path in sorted(records_dir.glob("*.md"), reverse=True):
        title = _first_heading(path)
        lines.append(f"- `{path.name}`：{title}")
    return lines


def _first_heading(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return "未命名策略记录"
