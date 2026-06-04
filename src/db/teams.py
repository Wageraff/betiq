"""Справочник команд / соперников."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Team
from src.scraper.utils.team_names import normalize_team_name


async def get_or_create_team(
    session: AsyncSession,
    name: str,
    *,
    sport: Optional[str] = None,
) -> Team:
    """Найти или создать запись в справочнике по нормализованному ключу."""
    display = (name or "").strip()
    key = normalize_team_name(display)
    if not key:
        raise ValueError(f"Cannot normalize team name: {name!r}")

    team = await session.scalar(select(Team).where(Team.normalized_key == key))
    if team:
        if sport and not team.sport:
            team.sport = sport
        if display and team.display_name != display:
            # Оставляем display_name редактируемым в админке; обновляем только если пусто
            if not team.display_name or team.display_name == team.normalized_key:
                team.display_name = display
        return team

    team = Team(
        normalized_key=key,
        display_name=display or key,
        sport=sport,
    )
    session.add(team)
    await session.flush()
    return team
