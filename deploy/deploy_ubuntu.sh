#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_DIR="${PROJECT_DIR:-$DEFAULT_PROJECT_DIR}"
REPO_URL="${REPO_URL:-}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if [[ -z "$REPO_URL" && ! -d "$PROJECT_DIR/.git" ]]; then
  echo "REPO_URL is required for first deployment."
  echo "Example: REPO_URL=https://github.com/you/fund-signal.git bash deploy/deploy_ubuntu.sh"
  exit 1
fi

if [[ ! -d "$PROJECT_DIR/.git" ]]; then
  git clone "$REPO_URL" "$PROJECT_DIR"
fi

cd "$PROJECT_DIR"

"$PYTHON_BIN" -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"

mkdir -p data/cache logs

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example. Fill FEISHU_WEBHOOK_URL before enabling --send."
else
  echo ".env already exists; leaving it unchanged."
fi

python -m fund_signal.cli check
python -m pytest -q
python -m fund_signal.cli run --mode afternoon --dry-run

echo
echo "Deployment check finished."
echo "Project: $PROJECT_DIR"
echo "Next:"
echo "1. Edit $PROJECT_DIR/.env"
echo "2. Test Feishu dry-run:"
echo "   cd $PROJECT_DIR && source .venv/bin/activate && python -m fund_signal.cli run --mode afternoon --dry-run --send"
