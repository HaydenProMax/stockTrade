#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$HOME/fund-signal}"

if [[ ! -d "$PROJECT_DIR/.git" ]]; then
  echo "Project git repository not found: $PROJECT_DIR"
  exit 1
fi

cd "$PROJECT_DIR"

git pull --ff-only

source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"

python -m fund_signal.cli check
python -m pytest -q
python -m fund_signal.cli run --mode afternoon --dry-run

echo
echo "Update check finished."
