"""Bulk fetch odds from The Odds API."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api_clients.constants import (
    ODDS_SPORT_KEYS_FOOTBALL,
    PROVIDER_THE_ODDS_API,
    SPORT_TO_ODDS_KEY,
    sport_for_odds_key,
)
from src.api_clients.external_ids import save_match_external_id
from src.api_clients.matching import event_matches_teams
from src.api_clients.odds import ingest_odds_api_event
from src.api_clients.the_odds_api import TheOddsApiClient
from src.db.models import Match

log = logging.getLogger("odds_sync")


def _parse_commence(iso: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


async def _match_by_odds_event_id(session: AsyncSession, event_id: str) -> Match | None:
    from src.db.models import MatchExternalId

    row = await session.scalar(
        select(MatchExternalId).where(
            MatchExternalId.provider == PROVIDER_THE_ODDS_API,
            MatchExternalId.external_id == event_id,
        )
    )
    if not row:
        return None
    return await session.get(Match, row.match_id)


async def _match_by_fuzzy(
    session: AsyncSession,
    *,
    sport: str,
    home: str,
    away: str,
    commence: datetime | None,
) -> Match | None:
    stmt = select(Match).where(Match.sport == sport)
    if commence is not None:
        window = timedelta(hours=3)
        stmt = stmt.where(
            Match.match_date >= commence - window,
            Match.match_date <= commence + window,
        )
    candidates = (await session.scalars(stmt)).all()
    for m in candidates:
        if await event_matches_teams(
            session,
            event_home=home,
            event_away=away,
            home_id=m.team_home_id,
            home_name=m.team_home,
            away_id=m.team_away_id,
            away_name=m.team_away,
            sport=m.sport,
        ):
            return m
    return None


async def sync_odds_for_sport_key(session: AsyncSession, sport_key: str) -> int:
    client = TheOddsApiClient()
    if not client.enabled:
        return 0
    events = await client.get_odds(sport_key)
    sport = sport_for_odds_key(sport_key)
    count = 0
    for event in events:
        event_id = event.get("id", "")
        match = await _match_by_odds_event_id(session, event_id)
        if not match:
            commence = _parse_commence(event.get("commence_time", ""))
            match = await _match_by_fuzzy(
                session,
                sport=sport,
                home=event.get("home_team", ""),
                away=event.get("away_team", ""),
                commence=commence,
            )
            if match and event_id:
                await save_match_external_id(
                    session,
                    match.id,
                    PROVIDER_THE_ODDS_API,
                    event_id,
                    confidence=0.85,
                )
        if match:
            count += await ingest_odds_api_event(session, match, event)
    await session.commit()
    return count


async def sync_all_odds(session: AsyncSession, *, football_only: bool = False) -> int:
    total = 0
    keys = ODDS_SPORT_KEYS_FOOTBALL if football_only else list(SPORT_TO_ODDS_KEY.values())
    for key in keys:
        try:
            total += await sync_odds_for_sport_key(session, key)
        except Exception:
            log.exception("Odds sync failed for %s", key)
    return total
