#!/usr/bin/env bash
# Запуск парсера с venv и PYTHONPATH (не используйте системный python3.11).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"
PY="$ROOT/venv/bin/python3.11"
if [[ ! -x "$PY" ]]; then
  PY="$ROOT/venv/bin/python3"
fi
if [[ ! -x "$PY" ]]; then
  echo "venv not found. Run: cd $ROOT && python3.11 -m venv venv && ./venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi
exec "$PY" -m src.scraper.engine "$@"
