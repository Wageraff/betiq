#!/usr/bin/env python3
"""Привязать teams к matches по Python normalize (кириллица и алиасы)."""
from __future__ import annotations

import asyncio

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
