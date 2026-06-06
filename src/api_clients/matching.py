"""Сопоставление с внешними API через канонические EN-ключи teams.normalized_key."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.api_clients.constants import PROVIDER_API_FOOTBALL
from src.api_clients.fuzzy import fuzzy_match
from src.db.models import Team, TeamExternalId
from src.scraper.utils.team_names import (
    canonical_team_display,
    canonical_team_key,
    resolve_team_key,
)


def api_name_to_key(name: str) -> str:
    return resolve_team_key(canonical_team_key(name))


def keys_match(key_a: str, key_b: str) -> bool:
    if not key_a or not key_b:
        return False
    return resolve_team_key(key_a) == resolve_team_key(key_b)


async def resolve_team_english(
    session: AsyncSession,
    team_id: int | None,
    fallback_name: str,
    *,
    sport: str | None = None,
) -> tuple[str, str]:
    """Канонический EN-ключ и display для сопоставления с API."""
    key = api_name_to_key(fallback_name)
    display = (
        canonical_team_display(key, raw_name=fallback_name, sport=sport)
        if key
        else (fallback_name or "")
    )

    if not team_id:
        return key, display

    team = await session.get(Team, team_id)
    if team:
        key = resolve_team_key(team.normalized_key) or key
        display = team.display_name or display

    ext = await session.get(TeamExternalId, (team_id, PROVIDER_API_FOOTBALL))
    if ext and ext.external_name:
        display = ext.external_name

    return key, display


def api_name_matches_team(api_name: str, team_key: str, team_display: str) -> bool:
    api_key = api_name_to_key(api_name)
    if api_key and team_key and keys_match(api_key, team_key):
        return True
    if team_display and fuzzy_match(api_name, team_display):
        return True
    return False


async def event_matches_teams(
    session: AsyncSession,
    *,
    event_home: str,
    event_away: str,
    home_id: int | None,
    home_name: str,
    away_id: int | None,
    away_name: str,
    sport: str | None = None,
) -> bool:
    home_key, home_display = await resolve_team_english(
        session, home_id, home_name, sport=sport
    )
    away_key, away_display = await resolve_team_english(
        session, away_id, away_name, sport=sport
    )
    return api_name_matches_team(event_home, home_key, home_display) and api_name_matches_team(
        event_away, away_key, away_display
    )
