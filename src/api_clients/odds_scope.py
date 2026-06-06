"""Окно предстоящих матчей и sport_key для синка odds (по данным БД)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api_clients.constants import (
    PROVIDER_API_FOOTBALL,
    PROVIDER_THE_ODDS_API,
)
from src.api_clients.odds_keys import odds_sport_keys_for_match
from src.config import settings
from src.db.models import Match, MatchExternalId, MatchOdds

_FINISHED_STATUSES = frozenset(
    {"FT", "AET", "PEN", "CANC", "ABD", "AWD", "WO", "PST"}
)


def upcoming_match_window() -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=settings.odds_skip_finished_hours)
    until = now + timedelta(days=settings.odds_upcoming_days_ahead)
    return since, until


def is_upcoming_match(match: Match, *, since: datetime, until: datetime) -> bool:
    if not match.match_date:
        return False
    if match.match_date < since or match.match_date > until:
        return False
    if match.status and match.status.upper() in _FINISHED_STATUSES:
        return False
    return True


async def upcoming_football_matches(session: AsyncSession) -> list[Match]:
    since, until = upcoming_match_window()
    rows = (
        await session.scalars(
            select(Match)
            .where(
                Match.sport == "football",
                Match.match_date.isnot(None),
                Match.match_date >= since,
                Match.match_date <= until,
            )
            .order_by(Match.match_date.asc())
        )
    ).all()
    return [m for m in rows if is_upcoming_match(m, since=since, until=until)]


async def collect_odds_sport_keys(
    session: AsyncSession, matches: list[Match]
) -> dict[str, list[Match]]:
    """sport_key → матчи, для которых он нужен."""
    by_key: dict[str, list[Match]] = {}
    for match in matches:
        for key in await odds_sport_keys_for_match(session, match):
            by_key.setdefault(key, []).append(match)
    return by_key


async def sport_keys_for_odds_sync(session: AsyncSession) -> list[str]:
    if settings.odds_sync_mode == "all_leagues":
        from src.api_clients.constants import ODDS_SPORT_KEYS_FOOTBALL

        return list(ODDS_SPORT_KEYS_FOOTBALL)
    matches = await upcoming_football_matches(session)
    by_key = await collect_odds_sport_keys(session, matches)
    return sorted(by_key.keys())


async def match_external_providers(
    session: AsyncSession, match_ids: list[int]
) -> dict[int, set[str]]:
    if not match_ids:
        return {}
    rows = (
        await session.execute(
            select(MatchExternalId.match_id, MatchExternalId.provider).where(
                MatchExternalId.match_id.in_(match_ids)
            )
        )
    ).all()
    out: dict[int, set[str]] = {}
    for mid, provider in rows:
        out.setdefault(mid, set()).add(provider)
    return out


async def match_odds_counts(
    session: AsyncSession, match_ids: list[int]
) -> dict[int, int]:
    if not match_ids:
        return {}
    rows = (
        await session.execute(
            select(MatchOdds.match_id, func.count())
            .where(MatchOdds.match_id.in_(match_ids))
            .group_by(MatchOdds.match_id)
        )
    ).all()
    return {mid: int(cnt) for mid, cnt in rows}
