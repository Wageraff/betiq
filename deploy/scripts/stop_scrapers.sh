#!/bin/bash
# Остановить все фоновые процессы BetIQ (scheduler, API, бот, ручные парсеры).
set -e
echo "Stopping systemd units..."
systemctl stop betiq-scheduler betiq-api betiq-telegram 2>/dev/null || true
echo "Killing stray Python scrapers..."
pkill -f "src.scraper.scheduler" 2>/dev/null || true
pkill -f "src.scraper.engine" 2>/dev/null || true
pkill -f "src.bot.telegram" 2>/dev/null || true
sleep 1
if pgrep -af "src.scraper|src.bot.telegram" >/dev/null 2>&1; then
  echo "Still running:"
  pgrep -af "src.scraper|src.bot.telegram" || true
else
  echo "All scrapers stopped."
fi
