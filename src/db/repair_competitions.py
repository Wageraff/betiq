"""Починка competition: ЧМ-2026 → World Cup, НХЛ → NHL, …"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api_clients.odds_scope import is_upcoming_match, upcoming_match_window
from src.db.models import Match
from src.scraper.utils.normalizer import (
    canonical_competition_name,
    competition_needs_canonicalization,
    infer_sport_from_competition,
)


async def repair_competition_names(
    session: AsyncSession, *, all_matches: bool = False
) -> int:
    """Нормализовать русские названия турниров в EN для предстоящих (или всех) матчей."""
    if all_matches:
        rows = (await session.scalars(select(Match))).all()
    else:
        since, until = upcoming_match_window()
        rows = (
            await session.scalars(
                select(Match).where(
                    Match.match_date.isnot(None),
                    Match.match_date >= since,
                    Match.match_date <= until,
                )
            )
        ).all()
        rows = [m for m in rows if is_upcoming_match(m, since=since, until=until)]

    updated = 0
    for match in rows:
        if not competition_needs_canonicalization(match.competition):
            continue
        canonical = canonical_competition_name(match.competition)
        if not canonical or canonical == match.competition:
            continue
        match.competition = canonical
        inferred = infer_sport_from_competition(canonical)
        if inferred:
            match.sport = inferred
        updated += 1
    return updated
