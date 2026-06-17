"""
APScheduler: полный парсинг каждые 4ч, быстрый — в :15 каждый час.
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
from src.scraper.proxy_pool import build_proxy_url

log = logging.getLogger("scheduler")


def _verify_proxy_pool() -> None:
    """Стартовая проверка: старый proxy_pool.py падает с username/_replace."""
    try:
        url = build_proxy_url(
            "http://user_area-RO_session-betiq001:pass@proxy.example.com:3120",
            "betiq004",
            "RU",
        )
    except ValueError as e:
        log.critical(
            "proxy_pool self-check failed (%s). "
            "На сервере старый код — выполните: cd /opt/betiq && git pull && "
            "sudo systemctl restart betiq-scheduler",
            e,
        )
        raise SystemExit(1) from e
    if "area-RU" not in url or "session-betiq004" not in url:
        log.critical("proxy_pool self-check: unexpected URL %s", url)
        raise SystemExit(1)
    log.info("proxy_pool self-check OK")

_JOB_KW = {"max_instances": 1, "coalesce": True}


async def job_repair_catalog() -> None:
    from src.db.repair_catalog import run_repair_catalog

    log.info("Scheduled: repair catalog (teams + matches)")
    stats = await run_repair_catalog()
    log.info("repair_catalog done: %s", stats)


async def job_full_scrape() -> None:
    limit = settings.scrape_full_limit
    log.info("Scheduled: full scrape (limit=%s)", limit)
    await run_scrape(limit=limit, mode="full")
    await job_repair_catalog()


async def job_quick_scrape() -> None:
    limit = settings.scrape_quick_limit
    log.info("Scheduled: quick scrape (limit=%s)", limit)
    await run_scrape(limit=limit, mode="quick")


async def job_ai_summaries() -> None:
    log.info("Scheduled: AI summaries")
    await run_summaries()


async def job_health_check() -> None:
    log.info("Scheduled: health check")
    await run_health_checks()


async def job_morning_digest() -> None:
    if not settings.telegram_morning_digest_enabled:
        return
    from src.bot.digest import send_morning_digest

    log.info("Scheduled: morning Telegram digest")
    await send_morning_digest()


def main() -> None:
    setup_logging()
    _verify_proxy_pool()
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
        CronTrigger.from_crontab("15 * * * *"),
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
    scheduler.add_job(
        job_repair_catalog,
        CronTrigger.from_crontab("30 3 * * *"),
        id="repair_catalog",
        replace_existing=True,
        **_JOB_KW,
    )
    if settings.telegram_morning_digest_enabled:
        scheduler.add_job(
            job_morning_digest,
            CronTrigger.from_crontab("5 8 * * *"),
            id="morning_digest",
            replace_existing=True,
            **_JOB_KW,
        )

    if settings.api_sync_enabled:
        from src.api_clients import jobs as api_jobs

        _api_jobs = [
            (api_jobs.job_sync_leagues, "0 6 * * *", "api_sync_leagues"),
            (api_jobs.job_sync_team_logos, "0 7 * * 1", "api_sync_team_logos"),
            (api_jobs.job_link_matches, "*/15 * * * *", "api_link_matches"),
            (api_jobs.job_fetch_team_form, "0 */6 * * *", "api_fetch_team_form"),
            (api_jobs.job_fetch_lineups, "0,30 * * * *", "api_fetch_lineups"),
            (api_jobs.job_fetch_odds, "*/30 * * * *", "api_fetch_odds"),
            (api_jobs.job_fetch_post_match_stats, "*/5 * * * *", "api_post_match_stats"),
            # Injuries, H2H, API-Predictions — каждый час; пропускают уже загруженные
            (api_jobs.job_fetch_injuries, "5 * * * *", "api_fetch_injuries"),
            (api_jobs.job_fetch_h2h, "20 * * * *", "api_fetch_h2h"),
            (api_jobs.job_fetch_api_predictions, "35 * * * *", "api_fetch_api_predictions"),
            (api_jobs.job_cleanup_ai_cache, "0 4 * * *", "api_cleanup_ai_cache"),
            (api_jobs.job_cleanup_old_data, "0 3 * * *", "api_cleanup_old_data"),
        ]
        for fn, cron, jid in _api_jobs:
            scheduler.add_job(fn, CronTrigger.from_crontab(cron), id=jid, **_JOB_KW)

    scheduler.start()
    log.info(
        "Scheduler started (full %sh limit=%s, quick hourly :15 limit=%s, "
        "AI 2h, health 08:00 UTC, digest 08:05 UTC, api_sync=%s)",
        "4",
        settings.scrape_full_limit,
        settings.scrape_quick_limit,
        settings.api_sync_enabled,
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
