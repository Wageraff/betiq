"""Загрузка URL из файла в очередь БД."""
import argparse
import sys
from pathlib import Path

from .settings import URLS_FILE, MIN_CONTENT_LENGTH, setup_logging
from .database import init_db, add_urls_to_queue, reset_urls_for_retry, reset_done_without_content
from .url_list import load_urls

import logging

log = logging.getLogger("url_loader")


def main():
    setup_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("input", nargs="?", default=URLS_FILE)
    args = parser.parse_args()
    path = Path(args.input)
    if not path.exists():
        log.error(f"Не найден: {path}")
        sys.exit(1)
    urls = load_urls(path)
    init_db()
    log.info(f"Загружено: {len(urls)} | новых: {add_urls_to_queue(urls)} | "
             f"retry: {reset_urls_for_retry(urls)} | recontent: {reset_done_without_content(urls, MIN_CONTENT_LENGTH)}")


if __name__ == "__main__":
    main()
