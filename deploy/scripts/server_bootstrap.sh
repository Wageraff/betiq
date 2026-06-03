#!/bin/bash
# Первичная привязка /opt/betiq к GitHub (запускать на сервере один раз).
#   export GIT_REPO=git@github.com:USER/betiq.git
#   sudo bash deploy/scripts/server_bootstrap.sh
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/betiq}"
GIT_REPO="${GIT_REPO:?Set GIT_REPO, e.g. git@github.com:you/betiq.git}"

if [[ -d "$APP_DIR/.git" ]]; then
  echo "Already a git repo: $APP_DIR"
  exit 0
fi

if [[ -d "$APP_DIR" ]] && [[ -n "$(ls -A "$APP_DIR" 2>/dev/null)" ]]; then
  echo "Backing up existing $APP_DIR -> ${APP_DIR}.bak.$(date +%Y%m%d%H%M%S)"
  mv "$APP_DIR" "${APP_DIR}.bak.$(date +%Y%m%d%H%M%S)"
fi

echo "Cloning $GIT_REPO -> $APP_DIR"
git clone "$GIT_REPO" "$APP_DIR"
cd "$APP_DIR"

mkdir -p logs
if [[ ! -f .env ]] && [[ -f .env.example ]]; then
  cp .env.example .env
  echo "Created .env from .env.example — edit secrets: nano $APP_DIR/.env"
fi
if [[ ! -f proxies.txt ]] && [[ -f proxies.txt.example ]]; then
  cp proxies.txt.example proxies.txt
  echo "Created proxies.txt from example — edit: nano $APP_DIR/proxies.txt"
fi

if [[ ! -d venv ]]; then
  python3.11 -m venv venv || python3 -m venv venv
  ./venv/bin/pip install -r requirements.txt
  ./venv/bin/playwright install chromium
  ./venv/bin/playwright install-deps chromium 2>/dev/null || true
fi

chmod +x deploy/scripts/*.sh
echo "Bootstrap done. Next: edit .env, docker compose up -d, alembic upgrade head, systemctl enable units."
