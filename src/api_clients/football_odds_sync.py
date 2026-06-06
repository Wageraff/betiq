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
    session: AsyncSession, *, limit: int | None = None
) -> int:
    """Загрузить prematch odds по fixture_id для связанных football-матчей."""
    if not settings.api_football_odds_enabled:
        return 0
    client = ApiFootballClient()
    if not client.enabled:
        return 0

    batch = limit if limit is not None else settings.api_football_odds_batch_size
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=1)
    until = now + timedelta(days=settings.api_football_odds_days_ahead)
    linked = select(MatchExternalId.match_id).where(
        MatchExternalId.provider == PROVIDER_API_FOOTBALL
    )
    matches = (
        await session.scalars(
            select(Match).where(
                Match.id.in_(linked),
                Match.sport == "football",
                Match.match_date.isnot(None),
                Match.match_date >= since,
                Match.match_date <= until,
            )
        )
    ).all()
    matches.sort(key=lambda m: m.match_date or datetime.max.replace(tzinfo=timezone.utc))
    matches = matches[:batch]

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
