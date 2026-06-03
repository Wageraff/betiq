"""Загрузка настроек из config.ini, proxies.txt и переменных окружения."""
from __future__ import annotations

import configparser
import logging
import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config.ini"
PROXIES_PATH = BASE_DIR / "proxies.txt"


def _read_config() -> configparser.ConfigParser:
    cp = configparser.ConfigParser(interpolation=None)
    if CONFIG_PATH.exists():
        cp.read(CONFIG_PATH, encoding="utf-8")
    return cp


_cfg = _read_config()
_scraper = _cfg["scraper"] if _cfg.has_section("scraper") else {}
_datetime = _cfg["datetime"] if _cfg.has_section("datetime") else {}
_logging = _cfg["logging"] if _cfg.has_section("logging") else {}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = (
        "postgresql+asyncpg://predictions:predictions@localhost:5432/predictions_db"
    )
    database_url_sync: str = (
        "postgresql://predictions:predictions@localhost:5432/predictions_db"
    )

    anthropic_api_key: str = ""
    telegram_bot_token: str = ""
    telegram_admin_chat_id: str = ""
    admin_api_key: str = ""
    port: int = 8000

    require_proxy: bool = _scraper.getboolean("require_proxy", fallback=True)
    headless: bool = _scraper.getboolean("headless", fallback=True)
    page_timeout: int = int(_scraper.get("page_timeout", fallback=60000))
    viewport_width: int = int(_scraper.get("viewport_width", fallback=1366))
    viewport_height: int = int(_scraper.get("viewport_height", fallback=768))
    scrape_delay_min: float = float(_scraper.get("min_delay", fallback=2.0))
    scrape_delay_max: float = float(_scraper.get("max_delay", fallback=5.0))
    scrape_max_retries: int = int(_scraper.get("max_retries", fallback=3))
    scrape_articles_max_age_days: int = int(_scraper.get("articles_max_age_days", fallback=7))

    # IANA: в какой зоне на сайте показывают время матча (RO → Europe/Bucharest)
    match_datetime_source_tz: str = _datetime.get(
        "source_timezone", fallback="Europe/Bucharest"
    )
    # В БД и API matchDate всегда в UTC (см. match_datetime.py)
    match_datetime_storage_tz: str = _datetime.get("storage_timezone", fallback="UTC")

    log_level: str = _logging.get("level", fallback="INFO")
    log_file: str = str(BASE_DIR / _logging.get("file", fallback="logs/app.log"))


settings = Settings()

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]


def load_proxies() -> list[str]:
    if not PROXIES_PATH.exists():
        return []
    proxies: list[str] = []
    with open(PROXIES_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                proxies.append(line)
    return proxies


def setup_logging() -> None:
    log_path = Path(settings.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(),
        ],
        force=True,
    )
