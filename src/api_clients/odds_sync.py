"""Bulk fetch odds from The Odds API."""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api_clients.constants import ODDS_SPORT_KEYS_FOOTBALL, SPORT_TO_ODDS_KEY
from src.api_clients.external_ids import get_match_external_id
from src.api_clients.fuzzy import fuzzy_match
from src.api_clients.odds import ingest_odds_api_event
from src.api_clients.constants import PROVIDER_THE_ODDS_API
from src.api_clients.the_odds_api import TheOddsApiClient
from src.db.models import Match

log = logging.getLogger("odds_sync")


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


async def sync_odds_for_sport_key(session: AsyncSession, sport_key: str) -> int:
    client = TheOddsApiClient()
    if not client.enabled:
        return 0
    events = await client.get_odds(sport_key)
    count = 0
    for event in events:
        match = await _match_by_odds_event_id(session, event.get("id", ""))
        if not match:
            home = event.get("home_team", "")
            away = event.get("away_team", "")
            candidates = (
                await session.scalars(
                    select(Match).where(Match.sport == "football").limit(200)
                )
            ).all()
            for m in candidates:
                if fuzzy_match(home, m.team_home) and fuzzy_match(away, m.team_away):
                    match = m
                    break
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
