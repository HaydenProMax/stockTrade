from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class KnowledgeHit:
    path: Path
    heading: str
    text: str
    score: int


@dataclass(frozen=True)
class KnowledgeSource:
    path: Path
    title: str
    chars: int


def list_knowledge_sources(root: Path) -> list[KnowledgeSource]:
    sources: list[KnowledgeSource] = []
    for path in _knowledge_paths(root):
        text = path.read_text(encoding="utf-8")
        sources.append(
            KnowledgeSource(
                path=path,
                title=_first_heading(text) or path.name,
                chars=len(text),
            )
        )
    return sources


def retrieve_markdown(
    root: Path,
    query: str,
    limit: int = 3,
    preferred_paths: set[Path] | None = None,
) -> list[KnowledgeHit]:
    terms = _query_terms(query)
    if not terms:
        return []

    preferred = {path.resolve() for path in preferred_paths or set()}
    hits: list[KnowledgeHit] = []
    for path in _knowledge_paths(root):
        is_preferred = path.resolve() in preferred
        for heading, text in _markdown_chunks(path):
            score = _score_chunk(heading, text, terms)
            if score <= 0:
                continue
            if is_preferred:
                score += 10
            hits.append(KnowledgeHit(path=path, heading=heading, text=text, score=score))

    hits.sort(key=lambda hit: (-_effective_score(root, hit), str(hit.path), hit.heading))
    return hits[:limit]


def format_knowledge_sources(root: Path) -> str:
    sources = list_knowledge_sources(root)
    lines = ["# 本地知识源", ""]
    if not sources:
        lines.extend(["未找到 Markdown 知识源。", ""])
        return "\n".join(lines)

    lines.extend(["| 文件 | 标题 | 字符数 |", "|---|---|---:|"])
    for source in sources:
        lines.append(
            "| "
            f"{_display_path(root, source.path)} | "
            f"{source.title} | "
            f"{source.chars} |"
        )
    lines.append("")
    return "\n".join(lines)


def format_knowledge_search(root: Path, query: str, limit: int = 5) -> str:
    hits = retrieve_markdown(root, query, limit=limit)
    lines = ["# 本地知识检索", "", f"查询：{query}", ""]
    if not hits:
        lines.extend(["没有检索到匹配片段。", ""])
        return "\n".join(lines)

    for hit in hits:
        lines.extend(
            [
                f"## {hit.heading}",
                "",
                f"- 来源：`{_display_path(root, hit.path)}`",
                f"- 分数：{hit.score}",
                "",
                hit.text,
                "",
            ]
        )
    return "\n".join(lines)


def _knowledge_paths(root: Path) -> list[Path]:
    paths: set[Path] = set()
    knowledge_dir = root / "knowledge"
    if knowledge_dir.exists():
        paths.update(
            path for path in knowledge_dir.rglob("*.md")
            if "archive" not in path.relative_to(knowledge_dir).parts
        )
    records_dir = root / "strategy_records"
    if records_dir.exists():
        paths.update(records_dir.glob("*.md"))
    return sorted(paths)


def _markdown_chunks(path: Path) -> list[tuple[str, str]]:
    text = path.read_text(encoding="utf-8")
    chunks: list[tuple[str, list[str]]] = []
    current_heading = path.name
    current_lines: list[str] = []

    for line in text.splitlines():
        if line.startswith("#"):
            if current_lines:
                chunks.append((current_heading, current_lines))
            current_heading = line.lstrip("#").strip() or path.name
            current_lines = [line]
        else:
            current_lines.append(line)

    if current_lines:
        chunks.append((current_heading, current_lines))

    return [
        (heading, _compact_text("\n".join(lines)))
        for heading, lines in chunks
        if _compact_text("\n".join(lines))
    ]


def _score_chunk(heading: str, text: str, terms: list[str]) -> int:
    heading_lower = heading.lower()
    text_lower = text.lower()
    score = 0
    for term in terms:
        term_lower = term.lower()
        if term_lower in heading_lower:
            score += 4
        score += min(text_lower.count(term_lower), 5)
    return score


def _source_priority(root: Path, path: Path) -> int:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return 0

    relative_text = str(relative).replace("\\", "/")
    if relative_text == "knowledge/personal_strategy.md":
        return 6
    if relative_text.startswith("strategy_records/") and path.stem.endswith("_current_monthly_plan"):
        return 5
    if relative_text.startswith("strategy_records/"):
        return -3
    return 0


def _effective_score(root: Path, hit: KnowledgeHit) -> int:
    priority = _source_priority(root, hit.path)
    if priority > 0:
        return hit.score + priority
    return hit.score


def _query_terms(query: str) -> list[str]:
    ascii_terms = re.findall(r"[A-Za-z0-9_]{2,}", query)
    # Chinese has no whitespace word boundaries, so a naive whole-run match
    # (e.g. "\u7684\u8d39\u7528\u662f\u591a\u5c11") almost never hits a chunk. Break each Han run into
    # overlapping bigrams, which is the standard lightweight CJK indexing unit.
    chinese_terms: list[str] = []
    for run in re.findall(r"[\u4e00-\u9fff]{2,}", query):
        chinese_terms.extend(run[index : index + 2] for index in range(len(run) - 1))
    terms = [*ascii_terms, *chinese_terms]
    deduped: list[str] = []
    for term in terms:
        if term not in deduped:
            deduped.append(term)
    return deduped


def _compact_text(text: str, max_chars: int = 700) -> str:
    compact = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3].rstrip() + "..."


def _first_heading(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return None


def _display_path(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)
