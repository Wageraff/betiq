"""Коэффициенты API-Football (/odds) для связанных football-матчей."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api_clients.api_football import ApiFootballClient
from src.api_clients.constants import PROVIDER_API_FOOTBALL
from src.api_clients.external_ids import get_match_external_id
from src.api_clients.odds import ingest_api_football_odds
from src.config import settings
from src.db.models import Match, MatchExternalId

log = logging.getLogger("football_odds_sync")


async def sync_api_football_odds(
    session: AsyncSession, *, limit: int = 30
) -> int:
    """Загрузить prematch odds по fixture_id для предстоящих связанных матчей."""
    if not settings.api_football_odds_enabled:
        return 0
    client = ApiFootballClient()
    if not client.enabled:
        return 0

    since = datetime.now(timezone.utc) - timedelta(days=1)
    until = datetime.now(timezone.utc) + timedelta(days=14)
    linked = select(MatchExternalId.match_id).where(
        MatchExternalId.provider == PROVIDER_API_FOOTBALL
    )
    matches = (
        await session.scalars(
            select(Match)
            .where(
                Match.id.in_(linked),
                Match.sport == "football",
                Match.match_date.isnot(None),
                Match.match_date >= since,
                Match.match_date <= until,
            )
            .order_by(Match.match_date.asc())
            .limit(limit)
        )
    ).all()

    total = 0
    for match in matches:
        fixture_id = await get_match_external_id(
            session, match.id, PROVIDER_API_FOOTBALL
        )
        if not fixture_id:
            continue
        try:
            rows = await client.get_fixture_odds(fixture_id)
            for row in rows:
                total += await ingest_api_football_odds(session, match, row)
        except Exception:
            log.exception("API-Football odds failed match_id=%s", match.id)
    await session.commit()
    return total
