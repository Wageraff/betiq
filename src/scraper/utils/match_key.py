"""Нормализация команд, match_key и дедупликация матчей."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Match
from src.db.teams import get_or_create_team
from src.scraper.utils.team_names import normalize_team_name

# Re-export for existing imports
__all__ = [
    "normalize_team_name",
    "build_match_key",
    "build_slug",
    "find_or_create_match",
]


def build_match_key(team_home: str, team_away: str, match_date: date) -> str:
    home = normalize_team_name(team_home)
    away = normalize_team_name(team_away)
    return f"{home}:{away}:{match_date.isoformat()}"


def build_slug(team_home: str, team_away: str, match_date: date) -> str:
    home = normalize_team_name(team_home)
    away = normalize_team_name(team_away)
    return f"{home}-vs-{away}-{match_date.strftime('%d-%m-%Y')}"


def _refresh_match_fields(match: Match, data: dict) -> None:
    """Обновить поля матча при повторном парсинге (sport, competition, команды)."""
    if data.get("team_home"):
        match.team_home = data["team_home"]
    if data.get("team_away"):
        match.team_away = data["team_away"]
    if data.get("sport"):
        match.sport = data["sport"]
    if data.get("competition") is not None:
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
            normalize_team_name(match.team_home) == home_norm
            and normalize_team_name(match.team_away) == away_norm
        ):
            return match
    return None


async def find_or_create_match(session: AsyncSession, data: dict) -> Match:
    """Найти существующий матч по ключу или создать новый."""
    match_dt: datetime = data["match_date"]
    day = _as_date(match_dt)
    key = build_match_key(data["team_home"], data["team_away"], day)
    home_norm = normalize_team_name(data["team_home"])
    away_norm = normalize_team_name(data["team_away"])

    match = await session.scalar(select(Match).where(Match.match_key == key))
    if match:
        _refresh_match_fields(match, data)
        await _link_teams(session, match, data)
        return match

    match = await _find_by_normalized_teams(session, home_norm, away_norm, day)
    if match:
        _refresh_match_fields(match, data)
        await _link_teams(session, match, data)
        return match

    match = Match(
        match_key=key,
        team_home=data["team_home"],
        team_away=data["team_away"],
        sport=data.get("sport"),
        competition=data.get("competition"),
        match_date=match_dt,
        slug=build_slug(data["team_home"], data["team_away"], day),
    )
    session.add(match)
    await session.flush()
    await _link_teams(session, match, data)
    return match
