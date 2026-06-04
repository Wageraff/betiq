"""Слияние дубликатов в справочнике teams."""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Match, Team
from src.scraper.utils.team_names import (
    canonical_team_display,
    merge_alias_text,
    normalize_team_name,
    resolve_team_key,
)


def _canonical_for_team(team: Team) -> str:
    from_display = normalize_team_name(team.display_name) if team.display_name else ""
    from_key = resolve_team_key(team.normalized_key)
    if from_display:
        return resolve_team_key(from_display)
    return from_key


async def dedupe_teams(session: AsyncSession, *, dry_run: bool = False) -> int:
    """Объединить строки teams с одним каноническим ключом; вернуть число удалённых."""
    teams = list(await session.scalars(select(Team).order_by(Team.id)))
    groups: dict[str, list[Team]] = defaultdict(list)
    for t in teams:
        groups[_canonical_for_team(t)].append(t)

    removed = 0
    for canon_key, group in groups.items():
        if not canon_key:
            continue
        group.sort(key=lambda t: (t.normalized_key != canon_key, t.id))
        keeper = group[0]
        canonical_name = canonical_team_display(canon_key)

        for dup in group[1:]:
            print(
                f"  team merge id={dup.id} ({dup.normalized_key!r} / {dup.display_name!r}) "
                f"-> id={keeper.id} ({canon_key})"
            )
            if dry_run:
                removed += 1
                continue
            await session.execute(
                update(Match)
                .where(Match.team_home_id == dup.id)
                .values(team_home_id=keeper.id)
            )
            await session.execute(
                update(Match)
                .where(Match.team_away_id == dup.id)
                .values(team_away_id=keeper.id)
            )
            keeper.aliases = merge_alias_text(
                keeper.aliases,
                dup.display_name,
                dup.normalized_key,
                dup.aliases or "",
            )
            await session.delete(dup)
            removed += 1

        if dry_run:
            continue
        keeper.normalized_key = canon_key
        if keeper.display_name != canonical_name:
            if keeper.display_name and keeper.display_name != canonical_name:
                keeper.aliases = merge_alias_text(keeper.aliases, keeper.display_name)
            keeper.display_name = canonical_name

    if not dry_run:
        await session.flush()
    return removed
