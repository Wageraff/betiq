#!/usr/bin/env python3
"""Привязать teams к matches по Python normalize (кириллица и алиасы).

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
from src.db.models import Match
from src.db.session import async_session_factory
from src.db.teams import get_or_create_team


async def main() -> None:
    setup_logging()
    async with async_session_factory() as session:
        matches = (await session.scalars(select(Match))).all()
        for m in matches:
            home = await get_or_create_team(session, m.team_home, sport=m.sport)
            away = await get_or_create_team(session, m.team_away, sport=m.sport)
            m.team_home_id = home.id
            m.team_away_id = away.id
        await session.commit()
        print(f"Updated {len(matches)} matches")


if __name__ == "__main__":
    asyncio.run(main())
