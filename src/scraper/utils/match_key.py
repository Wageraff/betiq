"""Нормализация команд, match_key и дедупликация матчей."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api_clients.constants import PROVIDER_API_FOOTBALL
from src.db.models import Match, MatchExternalId
from src.db.teams import get_or_create_team
from src.scraper.utils.normalizer import infer_sport_from_competition
from src.scraper.utils.match_key_build import build_match_key, build_slug
from src.scraper.utils.team_names import (
    canonical_team_display,
    canonical_team_key,
    normalize_team_name,
)

# Re-export for existing imports
__all__ = [
    "normalize_team_name",
    "canonical_team_key",
    "build_match_key",
    "build_slug",
    "find_or_create_match",
]


def _match_team_label(raw: str, sport: str | None) -> str:
    """Каноническое EN-имя для матча; локальное написание → teams.aliases."""
    raw = (raw or "").strip()
    if not raw:
        return raw
    key = canonical_team_key(raw)
    return canonical_team_display(key, raw_name=raw, sport=sport) or raw


async def _has_api_football_link(session: AsyncSession, match_id: int) -> bool:
    row = await session.scalar(
        select(MatchExternalId.match_id).where(
            MatchExternalId.match_id == match_id,
            MatchExternalId.provider == PROVIDER_API_FOOTBALL,
        )
    )
    return row is not None


def _refresh_match_fields(
    match: Match, data: dict, *, preserve_competition: bool = False
) -> None:
    """Обновить поля матча при повторном парсинге (sport, competition, команды)."""
    competition = data.get("competition") if data.get("competition") is not None else match.competition
    inferred = infer_sport_from_competition(competition)
    sport = inferred or data.get("sport") or match.sport
    if data.get("team_home"):
        match.team_home = _match_team_label(data["team_home"], sport)
    if data.get("team_away"):
        match.team_away = _match_team_label(data["team_away"], sport)
    if inferred or data.get("sport"):
        match.sport = sport
    if data.get("competition") is not None and not preserve_competition:
        match.competition = data["competition"] or match.competition
    if data.get("match_date"):
        match.match_date = data["match_date"]
        day = _as_date(data["match_date"])
        match.slug = build_slug(data["team_home"], data["team_away"], day)
        match.match_key = build_match_key(data["team_home"], data["team_away"], day)


def _as_date(value: date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    return value


async def _link_teams(session: AsyncSession, match: Match, data: dict) -> None:
    sport = data.get("sport")
    home = await get_or_create_team(session, data["team_home"], sport=sport)
    away = await get_or_create_team(session, data["team_away"], sport=sport)
    match.team_home_id = home.id
    match.team_away_id = away.id


async def _find_by_normalized_teams(
    session: AsyncSession,
    home_norm: str,
    away_norm: str,
    day: date,
) -> Match | None:
    """Матч с теми же нормализованными командами ±1 день (старый match_key в БД может отличаться)."""
    day_start = datetime.combine(day - timedelta(days=1), datetime.min.time())
    day_end = datetime.combine(day + timedelta(days=1), datetime.max.time())
    candidates = await session.scalars(
        select(Match).where(
            Match.match_date >= day_start,
            Match.match_date <= day_end,
        )
    )
    for match in candidates:
        if (
            canonical_team_key(match.team_home) == home_norm
            and canonical_team_key(match.team_away) == away_norm
        ):
            return match
    return None


async def find_or_create_match(session: AsyncSession, data: dict) -> Match:
    """Найти существующий матч по ключу или создать новый."""
    match_dt: datetime = data["match_date"]
    day = _as_date(match_dt)
    key = build_match_key(data["team_home"], data["team_away"], day)
    home_norm = canonical_team_key(data["team_home"])
    away_norm = canonical_team_key(data["team_away"])

    match = await session.scalar(select(Match).where(Match.match_key == key))
    if match:
        preserve = await _has_api_football_link(session, match.id)
        _refresh_match_fields(match, data, preserve_competition=preserve)
        await _link_teams(session, match, data)
        return match

    match = await _find_by_normalized_teams(session, home_norm, away_norm, day)
    if match:
        preserve = await _has_api_football_link(session, match.id)
        _refresh_match_fields(match, data, preserve_competition=preserve)
        await _link_teams(session, match, data)
        return match

    sport = data.get("sport")
    match = Match(
        match_key=key,
        team_home=_match_team_label(data["team_home"], sport),
        team_away=_match_team_label(data["team_away"], sport),
        sport=data.get("sport"),
        competition=data.get("competition"),
        match_date=match_dt,
        slug=build_slug(data["team_home"], data["team_away"], day),
    )
    session.add(match)
    await session.flush()
    await _link_teams(session, match, data)
    return match
