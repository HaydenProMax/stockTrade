from __future__ import annotations

import argparse
import os
from pathlib import Path

from fund_signal.advisor import answer_local_question
from fund_signal.config import load_config
from fund_signal.knowledge import (
    audit_fund_docs,
    import_external_markdown,
    import_fund_doc_section,
    write_fund_doc_templates,
    write_personal_strategy_markdown,
)
from fund_signal.notifier_feishu import send_text
from fund_signal.retriever import format_knowledge_search, format_knowledge_sources
from fund_signal.runner import run
from fund_signal.storage import Storage


def main() -> None:
    parser = argparse.ArgumentParser(prog="fund-signal")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument(
        "--mode",
        choices=["noon", "afternoon", "us_weekly", "manual"],
        default="manual",
    )
    run_parser.add_argument("--send", action="store_true")
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate signals and optionally send Feishu, but do not persist execution records.",
    )

    subparsers.add_parser("check")

    notify_parser = subparsers.add_parser("notify-test")
    notify_parser.add_argument(
        "--message",
        default="fund-signal 飞书机器人测试：配置已连通。",
    )

    knowledge_parser = subparsers.add_parser("build-knowledge")
    knowledge_parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output markdown path. Defaults to knowledge/personal_strategy.md.",
    )

    ask_parser = subparsers.add_parser("ask")
    ask_parser.add_argument("question", help="Local strategy question to answer from config and latest records.")

    subparsers.add_parser("knowledge-list")

    knowledge_search_parser = subparsers.add_parser("knowledge-search")
    knowledge_search_parser.add_argument("query", help="Search local markdown knowledge sources.")
    knowledge_search_parser.add_argument("--limit", type=int, default=5)

    fund_docs_parser = subparsers.add_parser("fund-docs-init")
    fund_docs_parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Fund docs directory. Defaults to knowledge/external/fund_docs.",
    )

    fund_docs_audit_parser = subparsers.add_parser("fund-docs-audit")
    fund_docs_audit_parser.add_argument(
        "--docs-dir",
        type=Path,
        default=None,
        help="Fund docs directory. Defaults to knowledge/external/fund_docs.",
    )
    fund_docs_audit_parser.add_argument(
        "--strict",
        action="store_true",
        help="Require official disclosure sources and reject third-party/vague placeholder wording.",
    )

    fund_docs_import_parser = subparsers.add_parser("fund-docs-import")
    fund_docs_import_parser.add_argument("fund_code")
    fund_docs_import_parser.add_argument("section")
    fund_docs_import_parser.add_argument("source_path", type=Path)
    fund_docs_import_parser.add_argument("--source-url", default=None)
    fund_docs_import_parser.add_argument("--material-date", default=None)
    fund_docs_import_parser.add_argument("--download-date", default=None)
    fund_docs_import_parser.add_argument(
        "--docs-dir",
        type=Path,
        default=None,
        help="Fund docs directory. Defaults to knowledge/external/fund_docs.",
    )

    external_docs_import_parser = subparsers.add_parser("external-docs-import")
    external_docs_import_parser.add_argument("category")
    external_docs_import_parser.add_argument("slug")
    external_docs_import_parser.add_argument("source_path", type=Path)
    external_docs_import_parser.add_argument("--title", default=None)
    external_docs_import_parser.add_argument("--source-url", default=None)
    external_docs_import_parser.add_argument("--material-date", default=None)
    external_docs_import_parser.add_argument("--download-date", default=None)
    external_docs_import_parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help="External docs root. Defaults to knowledge/external.",
    )
    external_docs_import_parser.add_argument("--overwrite", action="store_true")

    args = parser.parse_args()
    config = load_config(Path.cwd())

    if args.command == "check":
        Storage(config.root / "data" / "fund_signal.sqlite").init_schema()
        print("OK")
        return

    if args.command == "notify-test":
        webhook_url = os.getenv("FEISHU_WEBHOOK_URL")
        if not webhook_url:
            raise RuntimeError("Missing FEISHU_WEBHOOK_URL in environment or .env")
        webhook_secret = os.getenv("FEISHU_WEBHOOK_SECRET") or None
        response = send_text(webhook_url, args.message, webhook_secret)
        response.raise_for_status()
        print("Sent Feishu test message.")
        return

    if args.command == "build-knowledge":
        output_path = write_personal_strategy_markdown(config, args.output)
        print(f"Wrote {output_path}")
        return

    if args.command == "ask":
        print(answer_local_question(config, args.question))
        return

    if args.command == "knowledge-list":
        print(format_knowledge_sources(config.root))
        return

    if args.command == "knowledge-search":
        print(format_knowledge_search(config.root, args.query, limit=args.limit))
        return

    if args.command == "fund-docs-init":
        written = write_fund_doc_templates(config, args.output_dir)
        print(f"Wrote {len(written)} fund doc templates.")
        for path in written:
            print(path)
        return

    if args.command == "fund-docs-audit":
        print(audit_fund_docs(config, args.docs_dir, strict=args.strict))
        return

    if args.command == "fund-docs-import":
        path = import_fund_doc_section(
            config,
            args.fund_code,
            args.section,
            args.source_path,
            source_url=args.source_url,
            material_date=args.material_date,
            download_date=args.download_date,
            docs_dir=args.docs_dir,
        )
        print(f"Updated {path}")
        return

    if args.command == "external-docs-import":
        path = import_external_markdown(
            config,
            args.category,
            args.slug,
            args.source_path,
            title=args.title,
            source_url=args.source_url,
            material_date=args.material_date,
            download_date=args.download_date,
            output_root=args.output_root,
            overwrite=args.overwrite,
        )
        print(f"Wrote {path}")
        return

    if args.command == "run":
        print(run(config, mode=args.mode, send=args.send, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
