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
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import delete, select, update
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
    scrape_geo_context,
)
from src.scraper.health_check import _had_new_items_24h
from src.scraper.utils.alerter import (
    alert_layout_changed,
    alert_no_new_predictions,
    alert_scrape_error,
)
from src.scraper.utils.match_key import find_or_create_match
from src.scraper.utils.match_datetime import to_storage_datetime
from src.scraper.utils.normalizer import is_upcoming_match, parse_date_from_url
from src.scraper.utils import url_list_cache

log = logging.getLogger("engine")


@dataclass(frozen=True)
class SourceSnap:
    """Снимок полей Source до commit — ORM-объект после commit нельзя трогать в async."""

    id: int
    name: str
    language: str
    geo: str
    scraper_module: str
    is_active: bool
    base_url: str
    category_url: str
    last_success_at: Optional[datetime] = None


def _snap_source(source: Source) -> SourceSnap:
    return SourceSnap(
        id=source.id,
        name=source.name,
        language=source.language,
        geo=(source.geo or settings.proxy_fallback_geo or "GB").upper(),
        scraper_module=source.scraper_module or "",
        is_active=bool(source.is_active),
        base_url=source.base_url,
        category_url=source.category_url,
        last_success_at=source.last_success_at,
    )


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
    session: AsyncSession, snap: SourceSnap, data: dict
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

    data["match_date"] = to_storage_datetime(data["match_date"], geo=snap.geo)

    match = await find_or_create_match(session, data)
    pred = Prediction(
        match_id=match.id,
        source_id=snap.id,
        source_url=data["source_url"],
        title=data.get("title"),
        author=data.get("author"),
        language=snap.language,
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
    snap = _snap_source(source)
    started = time.monotonic()
    items_found = 0
    items_new = 0
    status = "success"
    error_msg = None

    if not snap.scraper_module:
        raise ValueError(f"Source {snap.name} has no scraper_module")

    module = load_source_module(snap.scraper_module)
    log.info("Scraping %s (%s)", snap.name, snap.scraper_module)
    category_url = snap.base_url.rstrip("/") + snap.category_url

    try:
        async with scrape_geo_context(snap.geo):
            async with page_session(verify_url=category_url) as (page, proxy):
                used_url_cache = False

                async def _collect_urls(*, refresh: bool = False) -> list[str]:
                    nonlocal used_url_cache
                    if refresh:
                        url_list_cache.invalidate(snap.id)
                    collected: list[str] | None = None
                    if not refresh and not force:
                        collected = url_list_cache.get(snap.id)
                    if collected is None:
                        collected = await module.get_article_urls(page)
                        url_list_cache.set(snap.id, collected)
                        if refresh:
                            used_url_cache = False
                    else:
                        used_url_cache = True
                        log.info(
                            "%s: skipped get_article_urls (cached %s URLs)",
                            snap.name,
                            len(collected),
                        )
                    return collected

                max_age = settings.scrape_articles_max_age_days

                def _new_urls_to_parse(
                    raw: list[str], known: set[str]
                ) -> list[str]:
                    filtered = [u for u in raw if _url_within_age(u, max_age)]
                    if force:
                        return filtered
                    return [u for u in filtered if u not in known]

                urls = await _collect_urls()
                items_found = len(urls)

                if force:
                    await _delete_predictions_by_urls(session, urls)
                    await session.commit()
                    log.info("%s: force re-scrape for %s URLs", snap.name, len(urls))

                known_urls = (
                    set() if force else await _existing_urls(session, urls)
                )
                to_parse = _new_urls_to_parse(urls, known_urls)
                if used_url_cache and not force and not to_parse:
                    log.info(
                        "%s: cache has no new URLs, refreshing listing",
                        snap.name,
                    )
                    urls = await _collect_urls(refresh=True)
                    items_found = len(urls)
                    known_urls = await _existing_urls(session, urls)
                    to_parse = _new_urls_to_parse(urls, known_urls)

                if not force:
                    aged = [u for u in urls if _url_within_age(u, max_age)]
                    db_skip = len(aged) - len(to_parse)
                    if db_skip:
                        log.info(
                            "%s: skip %s URLs already in DB",
                            snap.name,
                            db_skip,
                        )

                if limit:
                    to_parse = to_parse[:limit]

                log.info("%s: %s new URLs to parse", snap.name, len(to_parse))

                for url in to_parse:
                    parsed = None
                    for attempt in range(2):
                        try:
                            parsed = await module.parse_prediction(page, url)
                            break
                        except Exception as e:
                            report_proxy_failure(e, proxy)
                            if attempt == 0 and is_proxy_error(e):
                                log.warning("Proxy error, retry: %s", url)
                                continue
                            log.error("Failed %s: %s", url, e)
                            break

                    if parsed:
                        if await _persist_prediction(session, snap, parsed):
                            items_new += 1
                            await session.commit()
                            log.info("Saved: %s", url)
                        else:
                            await session.rollback()

                    delay = random.uniform(
                        settings.scrape_delay_min, settings.scrape_delay_max
                    )
                    await asyncio.sleep(delay)

            if status != "error":
                await session.execute(
                    update(Source)
                    .where(Source.id == snap.id)
                    .values(last_success_at=datetime.utcnow())
                )
        if items_new == 0 and items_found > 0:
            status = "partial"
        elif items_found == 0:
            status = "partial"

    except Exception as e:
        status = "error"
        error_msg = str(e)
        log.exception("Source %s failed: %s", snap.name, e)
        await session.rollback()

    duration_ms = int((time.monotonic() - started) * 1000)
    scrape_log = ScrapeLog(
        source_id=snap.id,
        status=status,
        items_found=items_found,
        items_new=items_new,
        error_msg=error_msg,
        duration_ms=duration_ms,
    )
    session.add(scrape_log)
    await session.execute(
        update(Source)
        .where(Source.id == snap.id)
        .values(last_checked_at=datetime.utcnow())
    )
    await session.commit()

    alert_ref = type("Source", (), {"name": snap.name, "id": snap.id})()
    if status == "error":
        await alert_scrape_error(
            alert_ref,
            error_msg or "unknown",
            last_success_at=snap.last_success_at,
        )
    elif items_found == 0:
        await alert_layout_changed(alert_ref)
    elif snap.is_active and not await _had_new_items_24h(session, snap.id):
        await alert_no_new_predictions(alert_ref)

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
