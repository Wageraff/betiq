"""Коэффициенты API-Football (/odds) для связанных football-матчей."""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api_clients.api_football import ApiFootballClient
from src.api_clients.constants import PROVIDER_API_FOOTBALL
from src.api_clients.external_ids import get_match_external_id
from src.api_clients.odds import ingest_api_football_odds
from src.api_clients.odds_scope import upcoming_football_matches
from src.config import settings
from src.db.models import Match, MatchExternalId

log = logging.getLogger("football_odds_sync")


async def sync_api_football_odds(
    session: AsyncSession, *, limit: int | None = None
) -> int:
    """Загрузить prematch odds по fixture_id для связанных football-матчей."""
    if not settings.api_football_odds_enabled:
        return 0
    client = ApiFootballClient()
    if not client.enabled:
        return 0

    batch = limit if limit is not None else settings.api_football_odds_batch_size
    all_upcoming = await upcoming_football_matches(session)
    linked_ids = set(
        await session.scalars(
            select(MatchExternalId.match_id).where(
                MatchExternalId.provider == PROVIDER_API_FOOTBALL
            )
        )
    )
    matches = [m for m in all_upcoming if m.id in linked_ids][:batch]

    total = 0
    checked = 0
    empty = 0
    for match in matches:
        fixture_id = await get_match_external_id(
            session, match.id, PROVIDER_API_FOOTBALL
        )
        if not fixture_id:
            continue
        checked += 1
        try:
            rows = await client.get_fixture_odds(fixture_id)
            if not rows:
                empty += 1
                log.info(
                    "API-Football odds empty fixture=%s match_id=%s",
                    fixture_id,
                    match.id,
                )
                continue
            for row in rows:
                total += await ingest_api_football_odds(session, match, row)
        except Exception:
            log.exception("API-Football odds failed match_id=%s", match.id)
    await session.commit()
    log.info(
        "API-Football odds sync: checked=%s empty=%s lines=%s window_days=%s",
        checked,
        empty,
        total,
        settings.api_football_odds_days_ahead,
    )
    return total


async def upcoming_af_odds_match_ids(session: AsyncSession) -> list[int]:
    """ID предстоящих football-матчей с привязкой API-Football (очередь /odds)."""
    linked_ids = set(
        await session.scalars(
            select(MatchExternalId.match_id).where(
                MatchExternalId.provider == PROVIDER_API_FOOTBALL
            )
        )
    )
    return [m.id for m in await upcoming_football_matches(session) if m.id in linked_ids]
