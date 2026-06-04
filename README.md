# Sports Predictions Aggregator

Backend pipeline for collecting sports betting predictions from multiple sources.

## Quick start

```bash
cp .env.example .env
cp proxies.txt.example proxies.txt   # add proxies if require_proxy=true
docker compose up -d
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
PYTHONPATH=. alembic upgrade head
```

## Scraper

```bash
# One source, max 5 new articles
PYTHONPATH=. python -m src.scraper.engine --source beturi --limit 5

# All active sources
PYTHONPATH=. python -m src.scraper.engine

# Scheduler (full scrape every 4h, quick every 30min, AI every 2h)
PYTHONPATH=. python -m src.scraper.scheduler

# AI summaries (matches with 2+ predictions); prompt template: prompts/ai_match_summary.txt
PYTHONPATH=. python -m src.ai.summarizer
PYTHONPATH=. python -m src.ai.summarizer --match-id 42 --print-prompt
PYTHONPATH=. python -m src.ai.summarizer --match-id 42 --force

# REST API
PYTHONPATH=. python -m src.api.main
# → http://localhost:8000/api/v1/matches
# → http://localhost:8000/api/v1/matches/{slug}
# → http://localhost:8000/docs

# Health check & diagnose
PYTHONPATH=. python -m src.scraper.health_check
PYTHONPATH=. python -m src.scraper.diagnose --source beturi

# Telegram bot (TELEGRAM_BOT_TOKEN + TELEGRAM_ADMIN_CHAT_ID in .env)
PYTHONPATH=. python -m src.bot.telegram
```

## Configuration

- `config.ini` — scraper delays, timeouts, logging
- `.env` — `DATABASE_URL`, `ANTHROPIC_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ADMIN_CHAT_ID`
- `proxies.txt` — one proxy per line (`http://user:pass@host:port`)

## Adding a source

1. Copy `src/scraper/sources/_template.py` → `src/scraper/sources/mysite.py`
2. Register in `src/scraper/sources/__init__.py`
3. Insert row into `sources` table (or add Alembic seed)
4. Run `python -m src.scraper.engine --source mysite --limit 3`

## Git & deploy на сервер

Файлы `.env` и `proxies.txt` **не в git** — на каждой машине свои копии.

### 1. Локально (Mac): создать репозиторий

```bash
cd /Users/alksy/betiq
git init
git add .
git commit -m "Initial commit: BetIQ aggregator"
```

Создайте **приватный** репозиторий на GitHub/GitLab, затем:

```bash
git remote add origin git@github.com:YOUR_USER/betiq.git
git branch -M main
git push -u origin main
```

### 2. Сервер: первый раз

```bash
# SSH-ключ сервера добавьте в GitHub: Settings → SSH keys
export GIT_REPO=git@github.com:YOUR_USER/betiq.git
sudo GIT_REPO="$GIT_REPO" bash /opt/betiq/deploy/scripts/server_bootstrap.sh
```

Если `/opt/betiq` уже есть с данными, скрипт переименует его в `/opt/betiq.bak.TIMESTAMP` и сделает `git clone`.  
Верните секреты: `cp /opt/betiq.bak.*/.env /opt/betiq/.env` и `proxies.txt`.

Настройте systemd (один раз):

```bash
sudo cp /opt/betiq/deploy/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable betiq-api betiq-scheduler betiq-telegram
```

### 3. Обычное обновление (после `git push` с Mac)

На сервере:

```bash
cd /opt/betiq
sudo bash deploy/scripts/deploy.sh
```

Или с Mac одной командой:

```bash
ssh root@vmi3342149 'cd /opt/betiq && git pull && sudo bash deploy/scripts/deploy.sh'
```

### 4. Остановить парсеры перед отладкой

```bash
sudo bash /opt/betiq/deploy/scripts/stop_scrapers.sh
```
