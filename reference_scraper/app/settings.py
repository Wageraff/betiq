"""
Загрузка настроек из config.ini и proxies.txt.
"""
import configparser
import logging
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config.ini"
PROXIES_PATH = BASE_DIR / "proxies.txt"


def _read_config() -> configparser.ConfigParser:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Не найден файл настроек: {CONFIG_PATH}")
    cp = configparser.ConfigParser(interpolation=None)
    cp.read(CONFIG_PATH, encoding="utf-8")
    return cp


_cfg = _read_config()

URLS_FILE = str(BASE_DIR / _cfg.get("urls", "input_file"))
FAILED_URLS_FILE = str(BASE_DIR / _cfg.get("urls", "failed_file"))
DIAGNOSE_TEST_URL = _cfg.get("urls", "diagnose_test_url", fallback="")

REQUIRE_PROXY = _cfg.getboolean("scraper", "require_proxy", fallback=True)
CONCURRENCY = _cfg.getint("scraper", "concurrency")
MIN_DELAY = _cfg.getfloat("scraper", "min_delay")
MAX_DELAY = _cfg.getfloat("scraper", "max_delay")
MAX_ATTEMPTS = _cfg.getint("scraper", "max_attempts")
PAGE_TIMEOUT = _cfg.getint("scraper", "page_timeout")
HEADLESS = _cfg.getboolean("scraper", "headless")
VIEWPORT_WIDTH = _cfg.getint("scraper", "viewport_width")
VIEWPORT_HEIGHT = _cfg.getint("scraper", "viewport_height")
MIN_CONTENT_LENGTH = _cfg.getint("scraper", "min_content_length", fallback=200)

SEL_CONTENT_BLOCKS = [
    s.strip() for s in _cfg.get("selectors", "content_block").split(",") if s.strip()
]
SEL_TITLE_H1 = _cfg.get("selectors", "title_h1", fallback="h1")

DB_PATH = str(BASE_DIR / _cfg.get("database", "path"))
API_HOST = _cfg.get("api", "host")
API_PORT = _cfg.getint("api", "port")
API_TOKEN = _cfg.get("api", "auth_token").strip()
LOG_LEVEL = _cfg.get("logging", "level")
LOG_FILE = str(BASE_DIR / _cfg.get("logging", "file"))


def load_proxies() -> list[str]:
    if not PROXIES_PATH.exists():
        return []
    proxies = []
    with open(PROXIES_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                proxies.append(line)
    return proxies


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
]


def setup_logging():
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
