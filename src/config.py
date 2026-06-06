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


def _parse_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]
_proxy_sessions = _cfg["proxy_sessions"] if _cfg.has_section("proxy_sessions") else {}
_datetime = _cfg["datetime"] if _cfg.has_section("datetime") else {}
_logging = _cfg["logging"] if _cfg.has_section("logging") else {}
_telegram = _cfg["telegram"] if _cfg.has_section("telegram") else {}
_api_sync = _cfg["api_sync"] if _cfg.has_section("api_sync") else {}
_ai = _cfg["ai"] if _cfg.has_section("ai") else {}


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
    # Claude API model ID (см. https://docs.anthropic.com — claude-sonnet-4-6)
    anthropic_model: str = _ai.get("model", fallback="claude-sonnet-4-6")
    # Шаблон промпта: {{team_home}}, {{predictions_block}}, … — см. prompts/README.md
    ai_prompt_template: str = _ai.get("prompt_template", fallback="prompts/ai_match_summary.txt")
    ai_analysis_max_chars: int = int(_ai.get("analysis_max_chars", fallback=500))
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
    # Пауза после серии ошибок прокси подряд (сек)
    scrape_proxy_error_cooldown_sec: float = float(
        _scraper.get("proxy_error_cooldown_sec", fallback=60)
    )
    scrape_proxy_error_burst: int = int(_scraper.get("proxy_error_burst", fallback=5))
    # Кэш URL с листингов (мин); 55 ≈ между quick scrape 60m. 0 = выкл.
    scrape_url_list_cache_ttl_minutes: int = int(
        _scraper.get("url_list_cache_ttl_minutes", fallback=55)
    )
    # Блокировка image/font/media/stylesheet и типичной рекламы в Playwright
    scrape_block_heavy_resources: bool = _scraper.getboolean(
        "block_heavy_resources", fallback=True
    )
    # Если area-{geo} источника недоступен — проверяем прокси с этим geo (обычно RO)
    proxy_fallback_geo: str = _scraper.get("proxy_fallback_geo", fallback="GB")
    # Лимиты scheduler: quick в :15 каждый час, full каждые 4h
    scrape_quick_limit: int = int(_scraper.get("quick_scrape_limit", fallback=3))
    scrape_full_limit: int = int(_scraper.get("full_scrape_limit", fallback=20))
    scrape_skip_if_empty_minutes: int = int(
        _scraper.get("scrape_skip_if_empty_minutes", fallback=55)
    )
    source_stats_days: int = int(_scraper.get("source_stats_days", fallback=7))

    # IANA: в какой зоне на сайте показывают время матча (RO → Europe/Bucharest)
    match_datetime_source_tz: str = _datetime.get(
        "source_timezone", fallback="Europe/Bucharest"
    )
    # В БД и API matchDate всегда в UTC (см. match_datetime.py)
    match_datetime_storage_tz: str = _datetime.get("storage_timezone", fallback="UTC")

    log_level: str = _logging.get("level", fallback="INFO")
    log_file: str = str(BASE_DIR / _logging.get("file", fallback="logs/app.log"))

    telegram_alert_dedup_hours: int = int(
        _telegram.get("alert_dedup_hours", fallback=24)
    )
    telegram_alert_snooze_hours: int = int(
        _telegram.get("alert_snooze_hours", fallback=6)
    )
    telegram_morning_digest_enabled: bool = _telegram.getboolean(
        "morning_digest_enabled", fallback=True
    )

    api_football_key: str = ""
    the_odds_api_key: str = ""
    api_sync_enabled: bool = _api_sync.getboolean("enabled", fallback=False)
    api_link_batch_size: int = int(_api_sync.get("link_batch_size", fallback=50))
    the_odds_api_markets: str = _api_sync.get(
        "odds_markets",
        fallback="h2h,spreads,totals",
    )
    the_odds_api_event_markets: str = _api_sync.get(
        "odds_event_markets",
        fallback="btts,draw_no_bet,alternate_spreads,alternate_totals",
    )
    the_odds_api_event_batch_size: int = int(
        _api_sync.get("odds_event_batch_size", fallback=40)
    )
    api_football_odds_enabled: bool = _api_sync.getboolean(
        "api_football_odds_enabled", fallback=True
    )
    api_football_odds_days_ahead: int = int(
        _api_sync.get("api_football_odds_days_ahead", fallback=365)
    )
    api_football_odds_batch_size: int = int(
        _api_sync.get("api_football_odds_batch_size", fallback=50)
    )
    api_fixture_refresh_limit: int = int(
        _api_sync.get("fixture_refresh_limit", fallback=80)
    )
    odds_sync_mode: str = _api_sync.get("odds_sync_mode", fallback="db_matches")
    odds_upcoming_days_ahead: int = int(
        _api_sync.get("odds_upcoming_days_ahead", fallback=365)
    )
    odds_skip_finished_hours: int = int(
        _api_sync.get("odds_skip_finished_hours", fallback=3)
    )
    admin_match_odds_limit: int = int(
        _api_sync.get("admin_match_odds_limit", fallback=500)
    )
    odds_min_interval_minutes: int = int(
        _api_sync.get("odds_min_interval_minutes", fallback=30)
    )
    api_quota_alert_threshold: int = int(
        _api_sync.get("api_quota_alert_threshold", fallback=100)
    )


settings = Settings()

source_tier_high = _parse_csv(
    _scraper.get("source_tier_high", fallback="vseprosport_ru,stavkiprognozy_ru")
)
source_tier_medium = _parse_csv(
    _scraper.get(
        "source_tier_medium",
        fallback="legalbet_ru,metaratings_ru,betonmobile_ru,legalbet",
    )
)
source_tier_low = _parse_csv(
    _scraper.get("source_tier_low", fallback="beturi,pontulzilei")
)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]


DEFAULT_PROXY_SESSIONS: dict[str, str] = {
    "legalbet": "betiq001",
    "pontulzilei": "betiq002",
    "beturi": "betiq003",
    "legalbet_ru": "betiq004",
    "metaratings_ru": "betiq005",
    "vseprosport_ru": "betiq006",
    "stavkiprognozy_ru": "betiq007",
    "betonmobile_ru": "betiq008",
}


def load_proxy_sessions() -> dict[str, str]:
    """scraper_module → session-id (без префикса session-)."""
    if _proxy_sessions:
        return {k.strip(): v.strip() for k, v in _proxy_sessions.items()}
    return dict(DEFAULT_PROXY_SESSIONS)


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
