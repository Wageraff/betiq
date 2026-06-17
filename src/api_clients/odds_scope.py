"""Окно предстоящих матчей и sport_key для синка odds (по данным БД)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api_clients.odds_keys import (
    all_football_odds_keys,
    all_non_football_odds_keys,
    odds_sport_keys_for_match,
)
from src.config import settings
from src.db.models import Competition, Match, MatchExternalId, MatchOdds

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


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def match_within_event_odds_window(match: Match) -> bool:
    """Per-event odds только за N часов до kickoff (см. odds_event_hours_ahead)."""
    if not match.match_date:
        return False
    now = datetime.now(timezone.utc)
    kickoff = _as_utc(match.match_date)
    if kickoff <= now:
        return False
    horizon = now + timedelta(hours=settings.odds_event_hours_ahead)
    return kickoff <= horizon


def match_odds_recently_fetched(match: Match) -> bool:
    """Пропуск повторного запроса, если odds_fetched_at свежее odds_fresh_skip_minutes."""
    if not match.odds_fetched_at:
        return False
    age_sec = (
        datetime.now(timezone.utc) - _as_utc(match.odds_fetched_at)
    ).total_seconds()
    return age_sec < settings.odds_fresh_skip_minutes * 60


def _competition_sync_clause(sync_field: str):
    col = getattr(Competition, sync_field)
    return or_(Match.competition_id.is_(None), col.is_(True))


async def upcoming_matches(
    session: AsyncSession,
    *,
    sports: set[str] | None = None,
    for_odds_sync: bool = False,
    for_stats_sync: bool = False,
    for_lineups_sync: bool = False,
) -> list[Match]:
    since, until = upcoming_match_window()
    stmt = select(Match).where(
        Match.match_date.isnot(None),
        Match.match_date >= since,
        Match.match_date <= until,
    )
    if for_odds_sync or for_stats_sync or for_lineups_sync:
        stmt = select(Match).join(
            Competition, Match.competition_id == Competition.id, isouter=True
        ).where(
            Match.match_date.isnot(None),
            Match.match_date >= since,
            Match.match_date <= until,
        )
        if for_odds_sync:
            stmt = stmt.where(_competition_sync_clause("sync_odds"))
        if for_stats_sync:
            stmt = stmt.where(_competition_sync_clause("sync_stats"))
        if for_lineups_sync:
            stmt = stmt.where(_competition_sync_clause("sync_lineups"))
    if sports:
        stmt = stmt.where(Match.sport.in_(sorted(sports)))
    rows = (await session.scalars(stmt.order_by(Match.match_date.asc()))).all()
    return [m for m in rows if is_upcoming_match(m, since=since, until=until)]


async def upcoming_football_matches(
    session: AsyncSession, *, for_odds_sync: bool = False
) -> list[Match]:
    return await upcoming_matches(
        session, sports={"football"}, for_odds_sync=for_odds_sync
    )


async def collect_odds_sport_keys(
    session: AsyncSession, matches: list[Match]
) -> dict[str, list[Match]]:
    by_key: dict[str, list[Match]] = {}
    for match in matches:
        for key in await odds_sport_keys_for_match(session, match):
            by_key.setdefault(key, []).append(match)
    return by_key


async def sport_keys_for_odds_sync(
    session: AsyncSession, *, sports: set[str] | None = None
) -> list[str]:
    if settings.odds_sync_mode == "all_leagues":
        keys: list[str] = []
        if sports is None or "football" in sports:
            keys.extend(all_football_odds_keys())
        if sports is None or sports - {"football"}:
            keys.extend(all_non_football_odds_keys())
        seen: set[str] = set()
        out: list[str] = []
        for k in keys:
            if k not in seen:
                seen.add(k)
                out.append(k)
        return out

    matches = await upcoming_matches(session, sports=sports, for_odds_sync=True)
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
