"""Починить справочник teams и слить дубликаты matches."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.match_dedupe import dedupe_matches
from src.db.models import Match, Team
from src.db.session import async_session_factory
from src.db.team_dedupe import dedupe_teams
from src.db.teams import get_or_create_team, refresh_team_display_from_matches
from src.scraper.utils.team_names import (
    canonical_team_display,
    is_catalog_display_name,
    merge_alias_text,
    normalize_team_name,
    pick_best_display_raw,
    resolve_team_key,
)


async def _fix_team_displays(session: AsyncSession) -> int:
    """display_name: сборные EN; игроки — из названий в матчах."""
    n = 0
    matches = list(await session.scalars(select(Match)))
    names_by_key: dict[str, list[str]] = {}
    sports_by_key: dict[str, list[str]] = {}
    for m in matches:
        for label, sport in ((m.team_home, m.sport), (m.team_away, m.sport)):
            if not label:
                continue
            k = resolve_team_key(normalize_team_name(label))
            names_by_key.setdefault(k, []).append(label)
            if sport:
                sports_by_key.setdefault(k, []).append(sport)

    for t in await session.scalars(select(Team)):
        canon_key = resolve_team_key(t.normalized_key)
        sport = t.sport or (
            sports_by_key[canon_key][0] if sports_by_key.get(canon_key) else None
        )
        best = pick_best_display_raw(names_by_key.get(canon_key, []), canon_key)
        canonical = canonical_team_display(canon_key, raw_name=best or t.display_name, sport=sport)

        if refresh_team_display_from_matches(session, t):
            n += 1
            continue
        if is_catalog_display_name(t.display_name, canon_key, sport=sport) and t.display_name != canonical:
            t.aliases = merge_alias_text(t.aliases, t.display_name)
            t.display_name = canonical
            n += 1
    return n


async def run_repair_catalog(*, dry_run: bool = False) -> dict[str, int]:
    async with async_session_factory() as session:
        teams_removed = await dedupe_teams(session, dry_run=dry_run)
        if dry_run:
            matches_merged = await dedupe_matches(session, dry_run=True)
            await session.rollback()
            return {
                "teams_removed": teams_removed,
                "display_fixes": 0,
                "matches_merged": matches_merged,
            }

        await session.flush()

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
        matches_merged = await dedupe_matches(session, dry_run=False)
        await session.commit()

        return {
            "teams_removed": teams_removed,
            "display_fixes": fixed,
            "matches_merged": matches_merged,
        }
