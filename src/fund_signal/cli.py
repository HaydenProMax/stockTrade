from __future__ import annotations

import argparse
import os
from pathlib import Path

from fund_signal.config import load_config
from fund_signal.notifier_feishu import send_text
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

    if args.command == "run":
        print(run(config, mode=args.mode, send=args.send, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
