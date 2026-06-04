#!/usr/bin/env python3
"""
Парсинг списка URL и запись в БД (проверка склейки матча + AI).
Запуск на сервере:
  sudo systemctl stop betiq-scheduler
  cd /opt/betiq && export PYTHONPATH=/opt/betiq
  ./venv/bin/python3.11 scripts/ingest_urls.py --force URL1 URL2 ...
  ./venv/bin/python3.11 -m src.ai.summarizer --match-id 49 --force
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import delete, select

from src.config import setup_logging
from src.db.models import Match, Prediction, PredictionBet, Source
from src.db.session import async_session_factory
from src.scraper.engine import _persist_prediction
from src.scraper.sources import load_source_module
from src.scraper.utils.browser import (
    browser_lifecycle,
    ensure_proxy_configured,
    page_session,
    scrape_geo_context,
)
from src.scraper.utils.match_key import build_match_key, normalize_team_name

log = logging.getLogger("ingest_urls")

FRANCE_IVORY_URLS = [
    "https://legalbet.ro/centrul-de-pariere/france-ivory-coast-04-06-2026/",
    "https://beturi.ro/ponturi-pariuri/fotbal/international/franta-coasta-de-fildes-meciuri-amicale-04-06-2026/",
    "https://legalbet.ru/match-center/france-ivory-coast-04-06-2026/",
    "https://www.pontul-zilei.com/ponturi-pariuri/franta-vs-coasta-de-fildes-ponturi-pariuri-amical-4-iunie-2026/",
]

_HOST_MODULE = {
    "legalbet.ro": "legalbet",
    "legalbet.ru": "legalbet_ru",
    "metaratings.ru": "metaratings_ru",
    "www.metaratings.ru": "metaratings_ru",
    "vseprosport.ru": "vseprosport_ru",
    "www.vseprosport.ru": "vseprosport_ru",
    "beturi.ro": "beturi",
    "www.pontul-zilei.com": "pontulzilei",
    "pontul-zilei.com": "pontulzilei",
}


def _module_for_url(url: str) -> str:
    host = urlparse(url).netloc.lower().replace("www.", "")
    for pattern, name in _HOST_MODULE.items():
        if host == pattern or host.endswith("." + pattern):
            return name
    raise ValueError(f"Unknown host for URL: {url}")


async def _delete_url(session, url: str) -> None:
    await session.execute(delete(Prediction).where(Prediction.source_url == url))


async def ingest_urls(urls: list[str], *, force: bool, dry_run: bool) -> None:
    ensure_proxy_configured()
    results: list[tuple[str, int | None, str | None]] = []

    async with browser_lifecycle():
        async with async_session_factory() as session:
            for url in urls:
                module_name = _module_for_url(url)
                source = await session.scalar(
                    select(Source).where(Source.scraper_module == module_name)
                )
                if not source:
                    log.error("Source not in DB: %s (%s)", module_name, url)
                    results.append((url, None, None))
                    continue

                geo = (source.geo or "GB").upper()
                module = load_source_module(module_name)

                if force and not dry_run:
                    await _delete_url(session, url)
                    await session.commit()

                log.info("Parsing %s via %s (geo=%s)", url, module_name, geo)
                async with scrape_geo_context(geo):
                    async with page_session() as (page, _proxy):
                        data = await module.parse_prediction(page, url)

                if not data:
                    log.error("Parse failed: %s", url)
                    results.append((url, None, None))
                    continue

                day = data["match_date"].date() if data.get("match_date") else None
                key = (
                    build_match_key(data["team_home"], data["team_away"], day)
                    if day
                    else None
                )
                log.info(
                    "Parsed: %s vs %s | key=%s | bets=%s",
                    data["team_home"],
                    data["team_away"],
                    key,
                    len(data.get("bets") or []),
                )

                if dry_run:
                    results.append((url, None, key))
                    continue

                saved = await _persist_prediction(session, source, data)
                if saved:
                    await session.commit()
                    pred = await session.scalar(
                        select(Prediction).where(Prediction.source_url == url)
                    )
                    mid = pred.match_id if pred else None
                    results.append((url, mid, key))
                    log.info("Saved prediction match_id=%s", mid)
                else:
                    await session.rollback()
                    log.warning("Not saved (past match or invalid): %s", url)
                    results.append((url, None, key))

    print("\n=== Summary ===")
    match_ids = {m for _, m, _ in results if m}
    for url, mid, key in results:
        print(f"  {mid or '-':>5}  {key or 'n/a':40}  {url}")
    if len(match_ids) == 1:
        mid = match_ids.pop()
        print(f"\nOK: все прогнозы на match_id={mid}")
        print(f"AI: ./venv/bin/python3.11 -m src.ai.summarizer --match-id {mid} --force")
    elif len(match_ids) > 1:
        print(f"\nFAIL: разные match_id {match_ids} — проверьте normalize_team_name")
    else:
        print("\nНи один URL не сохранён — см. логи (дата матча в прошлом?)")


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(description="Ingest specific prediction URLs")
    parser.add_argument("urls", nargs="*", help="URLs to parse (default: France–Ivory test set)")
    parser.add_argument("--force", action="store_true", help="Re-scrape: delete existing row by URL")
    parser.add_argument("--dry-run", action="store_true", help="Parse only, no DB write")
    parser.add_argument("--france-ivory", action="store_true", help="Use built-in 4 test URLs")
    args = parser.parse_args()

    urls = list(args.urls)
    if args.france_ivory or not urls:
        urls = FRANCE_IVORY_URLS

    asyncio.run(ingest_urls(urls, force=args.force, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
