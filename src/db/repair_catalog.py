"""Починить справочник teams и слить дубликаты matches."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.match_dedupe import dedupe_matches
from src.db.models import Match, Team
from src.db.session import async_session_factory
from src.db.team_dedupe import dedupe_teams
from src.db.teams import get_or_create_team
from src.scraper.utils.team_names import (
    canonical_team_display,
    is_catalog_display_name,
    merge_alias_text,
    resolve_team_key,
)


async def _fix_team_displays(session: AsyncSession) -> int:
    n = 0
    for t in await session.scalars(select(Team)):
        canon_key = resolve_team_key(t.normalized_key)
        canonical = canonical_team_display(canon_key)
        if t.normalized_key != canon_key:
            t.normalized_key = canon_key
            n += 1
        if is_catalog_display_name(t.display_name, canon_key) and t.display_name != canonical:
            t.aliases = merge_alias_text(t.aliases, t.display_name)
            t.display_name = canonical
            n += 1
    return n


async def run_repair_catalog(*, dry_run: bool = False) -> dict[str, int]:
    async with async_session_factory() as session:
        teams_removed = await dedupe_teams(session, dry_run=dry_run)

        matches = list(await session.scalars(select(Match)))
        for m in matches:
            if m.team_home:
                m.team_home_id = (
                    await get_or_create_team(session, m.team_home, sport=m.sport)
                ).id
            if m.team_away:
                m.team_away_id = (
                    await get_or_create_team(session, m.team_away, sport=m.sport)
                ).id

        fixed = await _fix_team_displays(session)
        matches_merged = await dedupe_matches(session, dry_run=dry_run)

        if not dry_run:
            await session.commit()

        return {
            "teams_removed": teams_removed,
            "display_fixes": fixed,
            "matches_merged": matches_merged,
        }
