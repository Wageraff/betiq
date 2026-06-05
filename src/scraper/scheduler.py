"""
APScheduler: полный парсинг каждые 4ч, быстрый — каждые 30 мин.
Запуск: python -m src.scraper.scheduler
"""
from __future__ import annotations

import asyncio
import logging
import signal

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.ai.summarizer import run_summaries
from src.config import settings, setup_logging
from src.scraper.engine import run_scrape
from src.scraper.health_check import run_health_checks

log = logging.getLogger("scheduler")

_JOB_KW = {"max_instances": 1, "coalesce": True}


async def job_full_scrape() -> None:
    limit = settings.scrape_full_limit
    log.info("Scheduled: full scrape (limit=%s)", limit)
    await run_scrape(limit=limit)


async def job_quick_scrape() -> None:
    limit = settings.scrape_quick_limit
    log.info("Scheduled: quick scrape (limit=%s)", limit)
    await run_scrape(limit=limit)


async def job_ai_summaries() -> None:
    log.info("Scheduled: AI summaries")
    await run_summaries()


async def job_health_check() -> None:
    log.info("Scheduled: health check")
    await run_health_checks()


def main() -> None:
    setup_logging()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    scheduler = AsyncIOScheduler(event_loop=loop)
    scheduler.add_job(
        job_full_scrape,
        CronTrigger.from_crontab("0 */4 * * *"),
        id="full_scrape",
        replace_existing=True,
        **_JOB_KW,
    )
    scheduler.add_job(
        job_quick_scrape,
        CronTrigger.from_crontab("*/30 * * * *"),
        id="quick_scrape",
        replace_existing=True,
        **_JOB_KW,
    )
    scheduler.add_job(
        job_ai_summaries,
        CronTrigger.from_crontab("15 */2 * * *"),
        id="ai_summaries",
        replace_existing=True,
        **_JOB_KW,
    )
    scheduler.add_job(
        job_health_check,
        CronTrigger.from_crontab("0 8 * * *"),
        id="health_check",
        replace_existing=True,
        **_JOB_KW,
    )
    scheduler.start()
    log.info(
        "Scheduler started (full %sh limit=%s, quick 30m limit=%s, AI 2h, health 08:00 UTC)",
        "4",
        settings.scrape_full_limit,
        settings.scrape_quick_limit,
    )

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, scheduler.shutdown)

    try:
        loop.run_forever()
    finally:
        scheduler.shutdown(wait=False)
        loop.close()


if __name__ == "__main__":
    main()
