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

_admin_dist="$APP_DIR/admin-ui/dist/index.html"
if [[ -d "$APP_DIR/admin-ui" ]]; then
  _node_major=0
  if command -v node &>/dev/null; then
    _node_major="$(node -e 'console.log(parseInt(process.versions.node.split(".")[0], 10))' 2>/dev/null || echo 0)"
  fi
  if [[ "$_node_major" -ge 18 ]] && command -v npm &>/dev/null; then
    echo "==> admin-ui build (Node $_node_major)"
    (cd "$APP_DIR/admin-ui" && (npm ci --silent 2>/dev/null || npm install --silent) && npm run build)
  elif [[ -f "$_admin_dist" ]]; then
    echo "==> admin-ui: skip build (Node ${_node_major:-?} < 18; using committed admin-ui/dist)"
  else
    echo "WARN: admin-ui/dist missing and Node < 18 — install Node 20 or build locally and git push dist"
    echo "      See: deploy/scripts/install_node20.sh"
  fi
fi

echo "==> restart services (if installed)"
for unit in betiq-api betiq-scheduler betiq-telegram; do
  if systemctl list-unit-files "$unit.service" &>/dev/null; then
    systemctl restart "$unit" 2>/dev/null && echo "restarted $unit" || true
  fi
done

echo "Deploy done: $(git rev-parse --short HEAD)"
