"""Справочник команд / соперников."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Team
from src.scraper.utils.team_names import (
    canonical_team_display,
    is_catalog_display_name,
    legacy_keys_for,
    merge_alias_text,
    normalize_team_name,
)


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

    canonical = canonical_team_display(key, raw_name=raw)
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
        if is_catalog_display_name(team.display_name, key):
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
