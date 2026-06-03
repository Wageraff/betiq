"""
Ежедневная проверка доступности источников.
Запуск: python -m src.scraper.health_check
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings, setup_logging
from src.db.models import HealthCheck, ScrapeLog, Source
from src.db.session import async_session_factory
from src.scraper.sources import load_source_module
from src.scraper.utils.alerter import (
    alert_layout_changed,
    alert_no_new_predictions,
    alert_unreachable,
)
from src.scraper.utils.browser import (
    browser_lifecycle,
    page_session,
    scrape_geo_context,
    wait_cloudflare,
)

log = logging.getLogger("health_check")


@dataclass
class HealthCheckResult:
    is_accessible: bool
    status_code: Optional[int]
    html_structure_ok: bool
    articles_found: int
    stale_scrape: bool
    no_new_24h: bool
    details: str


async def _had_new_items_24h(session: AsyncSession, source_id: int) -> bool:
    since = datetime.utcnow() - timedelta(hours=24)
    row = await session.scalar(
        select(ScrapeLog.id)
        .where(
            ScrapeLog.source_id == source_id,
            ScrapeLog.items_new > 0,
            ScrapeLog.started_at >= since,
        )
        .limit(1)
    )
    return row is not None


async def check_source(session: AsyncSession, source: Source) -> HealthCheckResult:
    category_url = source.base_url.rstrip("/") + source.category_url
    status_code: Optional[int] = None
    is_accessible = False
    html_structure_ok = False
    articles_found = 0
    details_parts: list[str] = []

    if not source.scraper_module:
        return HealthCheckResult(
            is_accessible=False,
            status_code=None,
            html_structure_ok=False,
            articles_found=0,
            stale_scrape=True,
            no_new_24h=True,
            details="scraper_module not set",
        )

    source_geo = (source.geo or settings.proxy_fallback_geo or "GB").upper()

    try:
        async with scrape_geo_context(source_geo):
            async with page_session(verify_url=category_url) as (page, _proxy):
                is_accessible = True
                status_code = 200
                title = (await page.title()) or ""
                h1 = await page.evaluate(
                    "() => document.querySelector('h1')?.innerText?.trim() || ''"
                )
                cf_blocked = (
                    "just a moment" in title.lower()
                    or "attention required" in title.lower()
                )
                content = await page.content()
                cf_mitigated = "cf-mitigated" in content

                if cf_blocked:
                    details_parts.append("cloudflare_challenge")
                    await page.wait_for_timeout(10_000)
                    title = await page.title()
                    h1 = await page.evaluate(
                        "() => document.querySelector('h1')?.innerText?.trim() || ''"
                    )

                module = load_source_module(source.scraper_module)
                try:
                    urls = await module.get_article_urls(page)
                    articles_found = len(urls)
                except Exception as e:
                    details_parts.append(f"get_article_urls: {e}")
                    urls = []

                has_h1 = bool(h1)
                html_structure_ok = (
                    articles_found > 0
                    and has_h1
                    and not cf_blocked
                    and not cf_mitigated
                )
                details_parts.append(
                    f"title={title[:60]!r} h1={bool(h1)} urls={articles_found}"
                )

    except Exception as e:
        details_parts.append(f"error: {e}")
        log.exception("Health check failed for %s", source.name)

    last_ok = source.last_success_at
    if last_ok and last_ok.tzinfo:
        last_ok = last_ok.replace(tzinfo=None)
    stale_scrape = last_ok is None or last_ok < datetime.utcnow() - timedelta(hours=12)
    no_new_24h = False
    if source.is_active:
        no_new_24h = not await _had_new_items_24h(session, source.id)

    return HealthCheckResult(
        is_accessible=is_accessible,
        status_code=status_code,
        html_structure_ok=html_structure_ok,
        articles_found=articles_found,
        stale_scrape=stale_scrape,
        no_new_24h=no_new_24h,
        details="; ".join(details_parts),
    )


async def _save_and_alert(
    session: AsyncSession,
    source: Source,
    result: HealthCheckResult,
) -> HealthCheck:
    record = HealthCheck(
        source_id=source.id,
        is_accessible=result.is_accessible,
        status_code=result.status_code,
        html_structure_ok=result.html_structure_ok,
        alert_sent=False,
        details=result.details,
    )
    alerts: list[str] = []

    if not result.is_accessible:
        alerts.append("unreachable")
        await alert_unreachable(source, result.status_code)
    if not result.html_structure_ok and result.is_accessible:
        alerts.append("layout")
        await alert_layout_changed(source)
    if source.is_active and result.no_new_24h:
        alerts.append("no_new_24h")
        await alert_no_new_predictions(source)

    if alerts:
        record.alert_sent = True

    session.add(record)
    source.last_checked_at = datetime.utcnow()
    await session.commit()
    return record


async def run_health_checks(source_module: Optional[str] = None) -> int:
    checked = 0
    async with browser_lifecycle():
        async with async_session_factory() as session:
            q = select(Source)
            if source_module:
                q = q.where(Source.scraper_module == source_module)
            else:
                q = q.where(Source.is_active.is_(True))
            sources = (await session.scalars(q)).all()

            for source in sources:
                log.info("Health check: %s", source.name)
                result = await check_source(session, source)
                await _save_and_alert(session, source, result)
                checked += 1

    log.info("Health checks completed: %s", checked)
    return checked


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(description="Source health checks")
    parser.add_argument("--source", type=str, help="scraper_module name")
    args = parser.parse_args()
    asyncio.run(run_health_checks(source_module=args.source))


if __name__ == "__main__":
    main()
