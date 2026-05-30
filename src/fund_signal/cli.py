from __future__ import annotations

import argparse
from pathlib import Path

from fund_signal.config import load_config
from fund_signal.runner import run
from fund_signal.storage import Storage


def main() -> None:
    parser = argparse.ArgumentParser(prog="fund-signal")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--mode", choices=["noon", "afternoon", "manual"], default="manual")
    run_parser.add_argument("--send", action="store_true")

    subparsers.add_parser("check")

    args = parser.parse_args()
    config = load_config(Path.cwd())

    if args.command == "check":
        Storage(config.root / "data" / "fund_signal.sqlite").init_schema()
        print("OK")
        return

    if args.command == "run":
        print(run(config, mode=args.mode, send=args.send))


if __name__ == "__main__":
    main()
