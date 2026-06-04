#!/usr/bin/env python3
"""Привязать teams к matches; display_name на английском, варианты с сайтов — в aliases.

Запуск:
  cd /opt/betiq && ./venv/bin/python3.11 scripts/backfill_teams.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import select

from src.config import setup_logging
from src.db.models import Match, Team
from src.db.session import async_session_factory
from src.db.teams import get_or_create_team
from src.scraper.utils.team_names import (
    canonical_team_display,
    is_catalog_display_name,
    merge_alias_text,
)


async def _fix_catalog_display(session) -> int:
    teams = (await session.scalars(select(Team))).all()
    n = 0
    for t in teams:
        canonical = canonical_team_display(t.normalized_key)
        if not canonical:
            continue
        old = t.display_name
        if old and old != canonical and is_catalog_display_name(old, t.normalized_key):
            t.aliases = merge_alias_text(t.aliases, old)
            t.display_name = canonical
            n += 1
    return n


async def main() -> None:
    setup_logging()
    async with async_session_factory() as session:
        matches = (await session.scalars(select(Match))).all()
        for m in matches:
            home = await get_or_create_team(session, m.team_home, sport=m.sport)
            away = await get_or_create_team(session, m.team_away, sport=m.sport)
            m.team_home_id = home.id
            m.team_away_id = away.id
        renamed = await _fix_catalog_display(session)
        await session.commit()
        print(f"Updated {len(matches)} matches, fixed {renamed} team display names")


if __name__ == "__main__":
    asyncio.run(main())
