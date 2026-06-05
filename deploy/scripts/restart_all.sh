#!/bin/bash
# Полный перезапуск BetIQ: systemd, зомби Playwright/Chromium, Docker, проверки.
# Использование: cd /opt/betiq && sudo bash deploy/scripts/restart_all.sh
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/betiq}"
cd "$APP_DIR"

echo "==> 1. Остановка systemd"
for unit in betiq-scheduler betiq-api betiq-telegram; do
  systemctl stop "$unit" 2>/dev/null || true
done

echo "==> 2. Завершение процессов BetIQ / Playwright"
for pattern in \
  "src.scraper.scheduler" \
  "src.scraper.engine" \
  "src.api.main" \
  "src.bot.telegram" \
  "playwright.*chromium" \
  "ms-playwright.*chrome" \
  "headless_shell" \
  "uvicorn"
do
  pkill -f "$pattern" 2>/dev/null || true
done

sleep 2
pkill -9 -f "src.scraper|src.api.main|src.bot.telegram" 2>/dev/null || true
pkill -9 -f "playwright|ms-playwright|headless_shell" 2>/dev/null || true

echo "==> 3. Проверка порта 8000"
if command -v ss &>/dev/null; then
  ss -tlnp | grep ':8000 ' || echo "  порт 8000 свободен"
elif command -v lsof &>/dev/null; then
  lsof -i :8000 2>/dev/null || echo "  порт 8000 свободен"
fi

echo "==> 4. Docker (PostgreSQL)"
docker compose up -d
docker compose ps

echo "==> 5. Запуск сервисов"
bash "$APP_DIR/deploy/scripts/start_services.sh"

echo "==> 6. Проверка API"
sleep 2
curl -sf --max-time 5 http://127.0.0.1:8000/health | head -c 80
echo ""
curl -sf --max-time 10 -D - -o /dev/null -H "Accept-Encoding: gzip" \
  http://127.0.0.1:8000/admin | grep -iE 'HTTP/|content-encoding' || true

echo ""
echo "==> 7. Статус systemd"
systemctl is-active betiq-api betiq-scheduler betiq-telegram 2>/dev/null || true

echo ""
echo "Готово. Админка: http://$(hostname -I 2>/dev/null | awk '{print $1}'):8000/admin"
echo "Если в браузере всё ещё висит — попробуйте SSH-туннель:"
echo "  ssh -L 8000:127.0.0.1:8000 root@$(hostname -I 2>/dev/null | awk '{print $1}')"
echo "  затем http://localhost:8000/admin"
