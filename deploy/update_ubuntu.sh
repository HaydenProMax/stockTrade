#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_DIR="${PROJECT_DIR:-$DEFAULT_PROJECT_DIR}"

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
