#!/bin/bash
# Ручная отладка всех источников (scheduler должен быть остановлен).
set -e
cd "$(dirname "$0")/../.."
export PYTHONPATH="${PWD}"
PY="${PWD}/venv/bin/python3.11"
LIMIT="${1:-5}"

for src in beturi pontulzilei legalbet; do
  echo "========== diagnose: $src =========="
  "$PY" -m src.scraper.diagnose --source "$src" || true
  echo "========== engine --force: $src (limit=$LIMIT) =========="
  "$PY" -m src.scraper.engine --source "$src" --limit "$LIMIT" --force || true
done

echo "========== DB sample =========="
docker compose exec -T db psql -U predictions -d predictions_db -c \
  "SELECT m.id, m.team_home, m.team_away, m.sport, m.competition, m.match_date::date
   FROM matches m ORDER BY m.match_date DESC NULLS LAST, m.id DESC LIMIT 15;"
