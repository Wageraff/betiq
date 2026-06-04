#!/bin/bash
# Обновление кода на сервере после git pull.
# Использование: cd /opt/betiq && sudo bash deploy/scripts/deploy.sh
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/betiq}"
cd "$APP_DIR"

if [[ ! -d .git ]]; then
  echo "ERROR: $APP_DIR is not a git repository. Clone the repo first."
  exit 1
fi

echo "==> git pull"
git pull --ff-only

PY="${APP_DIR}/venv/bin/python3.11"
if [[ ! -x "$PY" ]]; then
  PY="${APP_DIR}/venv/bin/python3"
fi
if [[ ! -x "$PY" ]]; then
  echo "ERROR: venv not found. Run: python3.11 -m venv venv && ./venv/bin/pip install -r requirements.txt"
  exit 1
fi

echo "==> pip install"
"$PY" -m pip install -r requirements.txt -q

echo "==> alembic"
export PYTHONPATH="$APP_DIR"
"$PY" -m alembic upgrade head

if [[ -d "$APP_DIR/admin-ui" ]] && command -v npm &>/dev/null; then
  echo "==> admin-ui build"
  (cd "$APP_DIR/admin-ui" && npm ci --silent 2>/dev/null || npm install --silent) && npm run build
fi

echo "==> restart services (if installed)"
for unit in betiq-api betiq-scheduler betiq-telegram; do
  if systemctl list-unit-files "$unit.service" &>/dev/null; then
    systemctl restart "$unit" 2>/dev/null && echo "restarted $unit" || true
  fi
done

echo "Deploy done: $(git rev-parse --short HEAD)"
