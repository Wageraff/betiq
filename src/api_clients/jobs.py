"""Scheduled jobs для внешних API."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from src.api_clients.competitions_sync import sync_leagues_from_api_football
from src.api_clients.constants import PROVIDER_API_FOOTBALL
from src.api_clients.external_ids import get_team_external_id, sync_team_logo_from_api
from src.api_clients.football_odds_sync import sync_api_football_odds
from src.api_clients.linker import link_unlinked_matches
from src.api_clients.odds_cleanup import clear_all_odds_data
from src.api_clients.odds_sync import sync_all_odds
from src.api_clients.stats_sync import (
    sync_post_match_stats,
    sync_prematch_api_predictions,
    sync_prematch_forms,
    sync_prematch_h2h,
    sync_prematch_injuries,
    sync_upcoming_lineups,
)
from src.api_clients.ai_cache import cleanup_expired_cache
from src.api_clients.api_football import ApiFootballClient
from src.config import settings
from src.db.models import ApiQuotaSnapshot, Match, MatchOdds, OddsHistory, Team
from src.db.session import async_session_factory

log = logging.getLogger("api_jobs")


def api_sync_enabled() -> bool:
    return settings.api_sync_enabled and (
        bool(settings.api_football_key) or bool(settings.the_odds_api_key)
    )


async def job_sync_leagues() -> None:
    if not api_sync_enabled():
        return
    async with async_session_factory() as session:
        n = await sync_leagues_from_api_football(session)
        log.info("job_sync_leagues: %s", n)


async def job_sync_team_logos() -> None:
    if not settings.api_football_key:
        return
    client = ApiFootballClient()
    async with async_session_factory() as session:
        teams = (
            await session.scalars(
                select(Team).where(Team.logo_url.is_(None), Team.logo_path.is_(None))
            )
        ).all()
        updated = 0
        for team in teams:
            ext = await get_team_external_id(session, team.id, PROVIDER_API_FOOTBALL)
            if not ext:
                continue
            fixtures = await client.get_fixtures(team=int(ext), last=1)
            if not fixtures:
                continue
            side = "home"
            tdata = (fixtures[0].get("teams") or {}).get(side) or {}
            if str(tdata.get("id")) != str(ext):
                tdata = (fixtures[0].get("teams") or {}).get("away") or {}
            if await sync_team_logo_from_api(session, team, tdata.get("logo")):
                updated += 1
        await session.commit()
        log.info("job_sync_team_logos: %s", updated)


async def job_link_matches() -> None:
    if not api_sync_enabled():
        return
    async with async_session_factory() as session:
        stats = await link_unlinked_matches(session, limit=settings.api_link_batch_size)
        log.info("job_link_matches: %s", stats)


async def job_fetch_team_form() -> None:
    if not settings.api_football_key:
        return
    async with async_session_factory() as session:
        n = await sync_prematch_forms(session, hours=48)
        log.info("job_fetch_team_form: %s rows", n)


async def job_fetch_lineups() -> None:
    if not settings.api_football_key:
        return
    async with async_session_factory() as session:
        n = await sync_upcoming_lineups(session)
        log.info("job_fetch_lineups: %s", n)


async def job_fetch_odds(*, force: bool = False) -> None:
    """The Odds API — все виды спорта (db_matches) + API-Football /odds для football."""
    if not settings.the_odds_api_key and not settings.api_football_odds_enabled:
        return
    n_odds = 0
    n_af = 0
    if settings.the_odds_api_key:
        async with async_session_factory() as session:
            try:
                n_odds = await sync_all_odds(session, sports=None, force=force)
            except Exception:
                await session.rollback()
                log.exception("The Odds API sync failed")
    if settings.api_football_odds_enabled and settings.api_football_key:
        async with async_session_factory() as session:
            try:
                n_af = await sync_api_football_odds(session)
            except Exception:
                await session.rollback()
                log.exception("API-Football odds sync failed")
    log.info(
        "job_fetch_odds: the_odds_api=%s api_football=%s force=%s",
        n_odds,
        n_af,
        force,
    )


async def job_reset_odds(*, refetch: bool = True) -> None:
    """Удалить все коэффициенты в БД и опционально загрузить заново (текущий config)."""
    async with async_session_factory() as session:
        stats = await clear_all_odds_data(session)
    log.info("job_reset_odds: cleared %s", stats)
    if refetch:
        await job_fetch_odds(force=True)


async def job_fetch_odds_football() -> None:
    """Алиас для обратной совместимости (scripts, старый scheduler id)."""
    await job_fetch_odds()


async def job_fetch_odds_other() -> None:
    """Deprecated: объединено в job_fetch_odds."""
    await job_fetch_odds()


async def job_fetch_post_match_stats() -> None:
    if not settings.api_football_key:
        return
    async with async_session_factory() as session:
        n = await sync_post_match_stats(session)
        log.info("job_fetch_post_match_stats: %s", n)


async def job_fetch_injuries() -> None:
    """Травмы и дисквалификации для матчей в ближайшие 48ч."""
    if not settings.api_football_key:
        return
    async with async_session_factory() as session:
        n = await sync_prematch_injuries(session, hours=48)
        log.info("job_fetch_injuries: %s", n)


async def job_fetch_h2h() -> None:
    """H2H (последние очные встречи) для матчей в ближайшие 72ч — однократно."""
    if not settings.api_football_key:
        return
    async with async_session_factory() as session:
        n = await sync_prematch_h2h(session, hours=72)
        log.info("job_fetch_h2h: %s", n)


async def job_fetch_api_predictions() -> None:
    """Прогнозы API-Football (/predictions) для матчей в ближайшие 48ч — однократно."""
    if not settings.api_football_key:
        return
    async with async_session_factory() as session:
        n = await sync_prematch_api_predictions(session, hours=48)
        log.info("job_fetch_api_predictions: %s", n)


async def job_cleanup_ai_cache() -> None:
    async with async_session_factory() as session:
        n = await cleanup_expired_cache(session)
        log.info("job_cleanup_ai_cache: %s", n)


async def job_cleanup_old_data() -> None:
    """Удалить устаревшие odds_history, quota snapshots и match_odds завершённых матчей."""
    now = datetime.now(timezone.utc)
    cutoff_odds = now - timedelta(days=14)
    cutoff_quota = now - timedelta(days=30)
    cutoff_finished = now - timedelta(days=7)
    finished_statuses = ("FT", "AET", "PEN", "CANC")

    async with async_session_factory() as session:
        hist = await session.execute(
            delete(OddsHistory).where(OddsHistory.recorded_at < cutoff_odds)
        )
        quota = await session.execute(
            delete(ApiQuotaSnapshot).where(ApiQuotaSnapshot.recorded_at < cutoff_quota)
        )
        finished_ids = select(Match.id).where(
            Match.match_date.isnot(None),
            Match.match_date < cutoff_finished,
            Match.status.in_(finished_statuses),
        )
        odds = await session.execute(
            delete(MatchOdds).where(MatchOdds.match_id.in_(finished_ids))
        )
        await session.commit()
        log.info(
            "job_cleanup_old_data: odds_history=%s quota=%s match_odds=%s",
            hist.rowcount,
            quota.rowcount,
            odds.rowcount,
        )
