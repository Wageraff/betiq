"""
Универсальный движок парсинга: обход источников, retry, scrape_logs.
Запуск: python -m src.scraper.engine [--source beturi] [--limit 10]
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import random
import time
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings, setup_logging
from src.db.models import Match, Prediction, PredictionBet, ScrapeLog, Source
from src.db.session import async_session_factory
from src.scraper.sources import load_source_module
from src.scraper.utils.browser import (
    browser_lifecycle,
    ensure_proxy_configured,
    is_proxy_error,
    page_session,
    report_proxy_failure,
)
from src.scraper.health_check import _had_new_items_24h
from src.scraper.utils.alerter import (
    alert_layout_changed,
    alert_no_new_predictions,
    alert_scrape_error,
)
from src.scraper.utils.match_key import find_or_create_match
from src.scraper.utils.normalizer import is_upcoming_match, parse_date_from_url

log = logging.getLogger("engine")


def _url_within_age(url: str, max_days: int) -> bool:
    """Статья не старше max_days и день матча в slug — сегодня или позже."""
    d = parse_date_from_url(url)
    if not d:
        return True
    if d < date.today():
        return False
    return d <= date.today() + timedelta(days=max_days)


async def _existing_urls(session: AsyncSession, urls: list[str]) -> set[str]:
    if not urls:
        return set()
    result = await session.scalars(
        select(Prediction.source_url).where(Prediction.source_url.in_(urls))
    )
    return set(result.all())


async def _persist_prediction(
    session: AsyncSession, source: Source, data: dict
) -> bool:
    if not data.get("team_home") or not data.get("team_away"):
        log.warning("Skip %s: missing teams", data.get("source_url"))
        return False
    if not data.get("match_date"):
        log.warning("Skip %s: missing match_date", data.get("source_url"))
        return False

    if not is_upcoming_match(data["match_date"]):
        log.info("Skip %s: match already past (%s)", data.get("source_url"), data["match_date"])
        return False

    match = await find_or_create_match(session, data)
    pred = Prediction(
        match_id=match.id,
        source_id=source.id,
        source_url=data["source_url"],
        title=data.get("title"),
        author=data.get("author"),
        language=source.language,
        full_text=data.get("full_text"),
        published_at=data.get("published_at"),
    )
    session.add(pred)
    await session.flush()

    for i, bet in enumerate(data.get("bets") or []):
        session.add(
            PredictionBet(
                prediction_id=pred.id,
                bet_type=bet.get("bet_type"),
                bet_pick=bet.get("bet_pick"),
                odds=bet.get("odds"),
                is_main=bet.get("is_main", i == 0),
                sort_order=i,
            )
        )

    match.predictions_count = (match.predictions_count or 0) + 1
    match.updated_at = datetime.utcnow()
    return True


async def _delete_predictions_by_urls(session: AsyncSession, urls: list[str]) -> None:
    if not urls:
        return
    await session.execute(delete(Prediction).where(Prediction.source_url.in_(urls)))


async def scrape_source(
    session: AsyncSession,
    source: Source,
    limit: Optional[int] = None,
    *,
    force: bool = False,
) -> ScrapeLog:
    started = time.monotonic()
    items_found = 0
    items_new = 0
    status = "success"
    error_msg = None

    if not source.scraper_module:
        raise ValueError(f"Source {source.name} has no scraper_module")

    module = load_source_module(source.scraper_module)
    log.info("Scraping %s (%s)", source.name, source.scraper_module)

    try:
        async with page_session() as (page, proxy):
            urls = await module.get_article_urls(page)
            items_found = len(urls)

            max_age = settings.scrape_articles_max_age_days
            urls = [u for u in urls if _url_within_age(u, max_age)]

            if force:
                await _delete_predictions_by_urls(session, urls)
                await session.commit()
                log.info("%s: force re-scrape for %s URLs", source.name, len(urls))
            else:
                existing = await _existing_urls(session, urls)
                urls = [u for u in urls if u not in existing]

            if limit:
                urls = urls[:limit]

            log.info("%s: %s new URLs to parse", source.name, len(urls))

            for url in urls:
                parsed = None
                article_proxy = None
                for attempt in range(2):
                    try:
                        async with page_session() as (article_page, article_proxy):
                            parsed = await module.parse_prediction(article_page, url)
                        break
                    except Exception as e:
                        report_proxy_failure(e, article_proxy)
                        if attempt == 0 and is_proxy_error(e):
                            log.warning("Proxy error, retry: %s", url)
                            continue
                        log.error("Failed %s: %s", url, e)
                        break

                if parsed:
                    if await _persist_prediction(session, source, parsed):
                        items_new += 1
                        await session.commit()
                        log.info("Saved: %s", url)
                    else:
                        await session.rollback()

                delay = random.uniform(
                    settings.scrape_delay_min, settings.scrape_delay_max
                )
                await asyncio.sleep(delay)

        source.last_success_at = datetime.utcnow()
        if items_new == 0 and items_found > 0:
            status = "partial"
        elif items_found == 0:
            status = "partial"

    except Exception as e:
        status = "error"
        error_msg = str(e)
        log.exception("Source %s failed: %s", source.name, e)
        await session.rollback()

    duration_ms = int((time.monotonic() - started) * 1000)
    scrape_log = ScrapeLog(
        source_id=source.id,
        status=status,
        items_found=items_found,
        items_new=items_new,
        error_msg=error_msg,
        duration_ms=duration_ms,
    )
    session.add(scrape_log)
    source.last_checked_at = datetime.utcnow()
    await session.commit()

    if status == "error":
        await alert_scrape_error(
            source, error_msg or "unknown", last_success_at=source.last_success_at
        )
    elif items_found == 0:
        await alert_layout_changed(source)
    elif source.is_active and not await _had_new_items_24h(session, source.id):
        await alert_no_new_predictions(source)

    return scrape_log


async def run_scrape(
    source_name: Optional[str] = None,
    limit: Optional[int] = None,
    *,
    force: bool = False,
) -> None:
    ensure_proxy_configured()
    async with browser_lifecycle():
        async with async_session_factory() as session:
            q = select(Source)
            if source_name:
                q = q.where(Source.scraper_module == source_name)
            else:
                q = q.where(Source.is_active.is_(True))
            sources = (await session.scalars(q)).all()

            if not sources:
                if source_name:
                    log.warning("Source not found: %s", source_name)
                else:
                    log.warning("No active sources found")
                return

            for source in sources:
                await scrape_source(session, source, limit=limit, force=force)


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(description="Sports predictions scraper")
    parser.add_argument("--source", type=str, help="scraper_module name, e.g. beturi")
    parser.add_argument("--limit", type=int, help="Max new articles per source")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-scrape URLs (delete existing predictions for collected URLs first)",
    )
    args = parser.parse_args()

    try:
        asyncio.run(
            run_scrape(source_name=args.source, limit=args.limit, force=args.force)
        )
    except KeyboardInterrupt:
        log.info("Interrupted")


if __name__ == "__main__":
    main()
