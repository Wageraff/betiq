#!/bin/bash
# Запуск PostgreSQL (Docker) и фоновых сервисов BetIQ.
# Использование: cd /opt/betiq && sudo bash deploy/scripts/start_services.sh
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/betiq}"
cd "$APP_DIR"

echo "==> Docker (PostgreSQL)"
docker compose up -d
docker compose ps

echo "==> proxy_pool check"
PY="${APP_DIR}/venv/bin/python3.11"
if [[ ! -x "$PY" ]]; then PY="${APP_DIR}/venv/bin/python3"; fi
if ! grep -q '_rebuild_proxy_url' "$APP_DIR/src/scraper/proxy_pool.py"; then
  echo "  ERROR: старый proxy_pool.py — сначала: git pull"
  exit 1
fi
PYTHONPATH="$APP_DIR" "$PY" -c "from src.scraper.proxy_pool import build_proxy_url; build_proxy_url('http://u_area-RO_session-betiq001:p@h:3120','betiq004','RU')" \
  && echo "  proxy_pool OK" || exit 1

echo "==> systemd units"
for unit in betiq-api betiq-scheduler betiq-telegram; do
  if systemctl list-unit-files "${unit}.service" &>/dev/null; then
    systemctl start "$unit"
    systemctl is-active --quiet "$unit" && echo "  $unit: active" || echo "  $unit: FAILED"
  else
    echo "  WARN: $unit.service not installed (see instructions/admin.md §2)"
  fi
done

echo "==> stray manual scrapers (should be none)"
if pgrep -af "src.scraper.engine" >/dev/null 2>&1; then
  echo "  NOTE: manual engine still running:"
  pgrep -af "src.scraper.engine" || true
else
  echo "  OK: no manual engine"
fi

echo ""
echo "Scheduler: quick scrape every 30m (limit 5/source), full every 4h (UTC)."
echo "Logs: journalctl -u betiq-scheduler -f"
echo "Admin: http://<host>:8000/admin  API health: curl -s localhost:8000/health"
