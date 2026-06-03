#!/usr/bin/env bash
set -e
echo ">>> BetIQ Parser — установка..."
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3-pip git sqlite3 \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 \
    libatspi2.0-0 libwayland-client0

python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
python -m playwright install chromium
python -m playwright install-deps chromium
python -c "from app.database import init_db; init_db(); print('БД: data/pages.db')"

echo ""
echo "  1) config.ini — селекторы под источники"
echo "  2) proxies.txt — прокси (area-RU, sticky)"
echo "  3) urls.txt — список URL"
echo "  4) ./venv/bin/python -m app.scraper --limit 5"
echo "  5) bash run_parser.sh"
