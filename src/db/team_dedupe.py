"""Слияние дубликатов в справочнике teams."""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Match, Team
from src.scraper.utils.team_names import (
    canonical_team_display,
    canonical_team_key,
    merge_alias_text,
    resolve_team_key,
)


def _canonical_for_team(team: Team) -> str:
    """Один ключ для RU/RO/EN вариантов (display, key, aliases)."""
    candidates: list[str] = []
    if team.normalized_key:
        candidates.append(team.normalized_key)
    if team.display_name:
        candidates.append(team.display_name)
    if team.aliases:
        candidates.extend(p.strip() for p in team.aliases.split(",") if p.strip())
    keys = {
        resolve_team_key(canonical_team_key(c))
        for c in candidates
        if c
    }
    keys.discard("")
    if len(keys) == 1:
        return keys.pop()
    if team.display_name:
        return resolve_team_key(canonical_team_key(team.display_name))
    return resolve_team_key(team.normalized_key)


def find_duplicate_groups(teams: list[Team]) -> list[tuple[str, list[Team]]]:
    """Группы с одним каноническим ключом (2+ записи)."""
    groups: dict[str, list[Team]] = defaultdict(list)
    for t in teams:
        groups[_canonical_for_team(t)].append(t)
    out: list[tuple[str, list[Team]]] = []
    for canon_key, group in groups.items():
        if canon_key and len(group) >= 2:
            group.sort(key=lambda t: (t.normalized_key != canon_key, t.id))
            out.append((canon_key, group))
    return sorted(out, key=lambda x: x[0])


async def merge_team_into(
    session: AsyncSession,
    keeper: Team,
    dup: Team,
) -> None:
    """Перенести ссылки с dup на keeper и удалить dup."""
    if dup.id == keeper.id:
        return
    await session.execute(
        update(Match).where(Match.team_home_id == dup.id).values(team_home_id=keeper.id)
    )
    await session.execute(
        update(Match).where(Match.team_away_id == dup.id).values(team_away_id=keeper.id)
    )
    keeper.aliases = merge_alias_text(
        keeper.aliases,
        dup.display_name,
        dup.normalized_key,
        dup.aliases or "",
    )
    await session.delete(dup)


async def finalize_keeper(session: AsyncSession, keeper: Team, canon_key: str) -> Team:
    canonical_name = canonical_team_display(canon_key, sport=keeper.sport)
    keeper.normalized_key = canon_key
    if keeper.display_name != canonical_name:
        if keeper.display_name and keeper.display_name != canonical_name:
            keeper.aliases = merge_alias_text(keeper.aliases, keeper.display_name)
        keeper.display_name = canonical_name
    await session.flush()
    return keeper


async def merge_teams_by_ids(
    session: AsyncSession,
    keeper_id: int,
    duplicate_ids: list[int],
) -> Team:
    """Слить выбранные команды в keeper (один канонический ключ)."""
    keeper = await session.get(Team, keeper_id)
    if not keeper:
        raise ValueError(f"Team {keeper_id} not found")

    canon_key = _canonical_for_team(keeper)
    dup_ids = [i for i in duplicate_ids if i != keeper_id]
    if not dup_ids:
        return await finalize_keeper(session, keeper, canon_key)

    for dup_id in dup_ids:
        dup = await session.get(Team, dup_id)
        if not dup:
            raise ValueError(f"Team {dup_id} not found")
        dup_canon = _canonical_for_team(dup)
        if dup_canon != canon_key:
            raise ValueError(
                f"Team {dup_id} ({dup.normalized_key}) не совпадает с группой "
                f"{canon_key} (keeper {keeper_id})"
            )
        await merge_team_into(session, keeper, dup)

    return await finalize_keeper(session, keeper, canon_key)


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
        sports = {t.sport for t in group if t.sport}
        group_sport = sports.pop() if len(sports) == 1 else None
        canonical_name = canonical_team_display(canon_key, sport=group_sport)

        for dup in group[1:]:
            print(
                f"  team merge id={dup.id} ({dup.normalized_key!r} / {dup.display_name!r}) "
                f"-> id={keeper.id} ({canon_key})"
            )
            if dry_run:
                removed += 1
                continue
            await merge_team_into(session, keeper, dup)
            removed += 1

        if dry_run:
            continue
        await finalize_keeper(session, keeper, canon_key)

    if not dry_run:
        await session.flush()
    return removed
