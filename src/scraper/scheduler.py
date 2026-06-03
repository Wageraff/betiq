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
from src.config import setup_logging
from src.scraper.engine import run_scrape
from src.scraper.health_check import run_health_checks

log = logging.getLogger("scheduler")

QUICK_LIMIT = 5


async def job_full_scrape() -> None:
    log.info("Scheduled: full scrape")
    await run_scrape()


async def job_quick_scrape() -> None:
    log.info("Scheduled: quick scrape (limit=%s)", QUICK_LIMIT)
    await run_scrape(limit=QUICK_LIMIT)


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
    )
    scheduler.add_job(
        job_quick_scrape,
        CronTrigger.from_crontab("*/30 * * * *"),
        id="quick_scrape",
        replace_existing=True,
    )
    scheduler.add_job(
        job_ai_summaries,
        CronTrigger.from_crontab("15 */2 * * *"),
        id="ai_summaries",
        replace_existing=True,
    )
    scheduler.add_job(
        job_health_check,
        CronTrigger.from_crontab("0 8 * * *"),
        id="health_check",
        replace_existing=True,
    )
    scheduler.start()
    log.info(
        "Scheduler started (scrape 4h/30m, AI 2h, health 08:00 UTC)"
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
