#!/usr/bin/env bash
# One-time setup. Run from the repo root: ./setup.sh
set -euo pipefail
cd "$(dirname "$0")"

PY=${PYTHON:-python3}

if [ ! -d .venv ]; then
  echo "creating virtualenv..."
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "installing dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
  echo "created .env  <-- put your ANTHROPIC_API_KEY in it"
fi

python -m harness.workspace

echo
echo "done. next:"
echo "  source .venv/bin/activate"
echo "  edit .env and add your API key"
echo "  open level0_watch/README.md"
