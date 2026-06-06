"""Scheduled jobs для внешних API."""
from __future__ import annotations

import logging

from sqlalchemy import select

from src.api_clients.competitions_sync import sync_leagues_from_api_football
from src.api_clients.constants import PROVIDER_API_FOOTBALL
from src.api_clients.external_ids import get_team_external_id, sync_team_logo_from_api
from src.api_clients.linker import link_unlinked_matches
from src.api_clients.football_odds_sync import sync_api_football_odds
from src.api_clients.odds_sync import sync_all_odds
from src.api_clients.stats_sync import (
    sync_post_match_stats,
    sync_prematch_forms,
    sync_upcoming_lineups,
)
from src.api_clients.ai_cache import cleanup_expired_cache
from src.api_clients.api_football import ApiFootballClient
from src.config import settings
from src.db.models import Team
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


async def job_fetch_odds_football() -> None:
    if not settings.the_odds_api_key and not settings.api_football_odds_enabled:
        return
    async with async_session_factory() as session:
        n_odds = 0
        n_af = 0
        if settings.the_odds_api_key:
            n_odds = await sync_all_odds(session, football_only=True)
        if settings.api_football_odds_enabled and settings.api_football_key:
            n_af = await sync_api_football_odds(session)
        log.info(
            "job_fetch_odds_football: the_odds_api=%s api_football=%s",
            n_odds,
            n_af,
        )


async def job_fetch_odds_other() -> None:
    if not settings.the_odds_api_key:
        return
    async with async_session_factory() as session:
        n = await sync_all_odds(session, football_only=False)
        log.info("job_fetch_odds_other: %s lines", n)


async def job_fetch_post_match_stats() -> None:
    if not settings.api_football_key:
        return
    async with async_session_factory() as session:
        n = await sync_post_match_stats(session)
        log.info("job_fetch_post_match_stats: %s", n)


async def job_cleanup_ai_cache() -> None:
    async with async_session_factory() as session:
        n = await cleanup_expired_cache(session)
        log.info("job_cleanup_ai_cache: %s", n)
