"""Справочник команд / соперников."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Match, Team
from src.scraper.utils.team_names import (
    canonical_team_display,
    is_catalog_display_name,
    legacy_keys_for,
    merge_alias_text,
    normalize_team_name,
    pick_best_display_raw,
    resolve_team_key,
)


async def refresh_team_display_from_matches(session: AsyncSession, team: Team) -> bool:
    """Подставить display_name из team_home/team_away матчей (для теннисистов)."""
    key = resolve_team_key(team.normalized_key)
    rows = await session.execute(
        select(Match.team_home, Match.team_away, Match.sport).where(
            or_(Match.team_home_id == team.id, Match.team_away_id == team.id)
        )
    )
    candidates: list[str] = []
    sports: list[str] = []
    for home, away, sport in rows:
        if home:
            candidates.append(home)
        if away:
            candidates.append(away)
        if sport:
            sports.append(sport)
    best = pick_best_display_raw(candidates, key)
    if not best:
        return False
    sport = team.sport or (sports[0] if sports else None)
    new_display = canonical_team_display(key, raw_name=best, sport=sport)
    if new_display == team.display_name:
        return False
    if team.display_name and team.display_name != new_display:
        team.aliases = merge_alias_text(team.aliases, team.display_name)
    team.display_name = new_display
    if sport and not team.sport:
        team.sport = sport
    return True


async def get_or_create_team(
    session: AsyncSession,
    name: str,
    *,
    sport: Optional[str] = None,
) -> Team:
    """Найти или создать запись в справочнике по нормализованному ключу (EN)."""
    raw = (name or "").strip()
    key = normalize_team_name(raw)
    if not key:
        raise ValueError(f"Cannot normalize team name: {name!r}")

    canonical = canonical_team_display(key, raw_name=raw, sport=sport)
    lookup_keys = legacy_keys_for(key)

    candidates = (
        await session.scalars(select(Team).where(Team.normalized_key.in_(lookup_keys)))
    ).all()
    team = next((t for t in candidates if t.normalized_key == key), None)
    if not team and candidates:
        team = min(candidates, key=lambda t: t.id)
    if team and team.normalized_key != key:
        canonical_row = await session.scalar(
            select(Team).where(Team.normalized_key == key)
        )
        if canonical_row:
            team = canonical_row
    if team:
        if sport and not team.sport:
            team.sport = sport
        if raw and raw != canonical:
            team.aliases = merge_alias_text(team.aliases, raw)
        if is_catalog_display_name(team.display_name, key, sport=sport or team.sport):
            team.display_name = canonical
        return team

    team = Team(
        normalized_key=key,
        display_name=canonical,
        sport=sport,
        aliases=merge_alias_text(None, raw) if raw and raw != canonical else None,
    )
    session.add(team)
    await session.flush()
    return team
