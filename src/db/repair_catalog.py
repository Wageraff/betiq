"""Починить справочник teams и слить дубликаты matches."""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.match_dedupe import dedupe_matches
from src.db.models import Match, Team
from src.db.session import async_session_factory
from src.db.team_dedupe import dedupe_teams, merge_team_into
from src.db.teams import get_or_create_team
from src.scraper.utils.match_key import _match_team_label
from src.scraper.utils.team_names import (
    canonical_key_from_names,
    canonical_team_display,
    canonical_team_key,
    merge_alias_text,
    pick_best_display_raw,
    resolve_team_key,
)


def _match_team_context(
    matches: list[Match],
) -> tuple[dict[int, list[str]], dict[int, list[str]]]:
    """team_id → подписи команд и виды спорта из матчей."""
    labels: dict[int, list[str]] = defaultdict(list)
    sports: dict[int, list[str]] = defaultdict(list)
    for m in matches:
        for tid, label in ((m.team_home_id, m.team_home), (m.team_away_id, m.team_away)):
            if tid and label:
                labels[tid].append(label)
            if tid and m.sport:
                sports[tid].append(m.sport)
    return labels, sports


async def _fix_match_labels(session: AsyncSession) -> int:
    """team_home/team_away в матчах — канонические EN-имена."""
    n = 0
    for m in await session.scalars(select(Match)):
        sport = m.sport
        if m.team_home:
            label = _match_team_label(m.team_home, sport)
            if label and label != m.team_home:
                m.team_home = label
                n += 1
        if m.team_away:
            label = _match_team_label(m.team_away, sport)
            if label and label != m.team_away:
                m.team_away = label
                n += 1
    return n


async def _rebuild_all_teams(
    session: AsyncSession,
    matches: list[Match],
    *,
    dry_run: bool = False,
) -> int:
    """Пересчитать normalized_key + display_name из матчей и алиасов."""
    labels_by_id, sports_by_id = _match_team_context(matches)
    fixed = 0

    async with session.no_autoflush:
        for team in await session.scalars(select(Team)):
            candidates: list[str] = []
            if team.normalized_key:
                candidates.append(team.normalized_key)
            if team.display_name:
                candidates.append(team.display_name)
            if team.aliases:
                candidates.extend(
                    p.strip() for p in team.aliases.split(",") if p.strip()
                )
            candidates.extend(labels_by_id.get(team.id, []))

            new_key = canonical_key_from_names(*candidates)
            if not new_key:
                continue

            sport = team.sport or (
                sports_by_id[team.id][0] if sports_by_id.get(team.id) else None
            )
            matching = [
                c
                for c in candidates
                if c and resolve_team_key(canonical_team_key(c)) == new_key
            ]
            best_raw = pick_best_display_raw(matching, new_key) or team.display_name
            new_display = canonical_team_display(
                new_key, raw_name=best_raw, sport=sport
            )

            if team.normalized_key != new_key:
                existing = await session.scalar(
                    select(Team).where(
                        Team.normalized_key == new_key,
                        Team.id != team.id,
                    )
                )
                if existing:
                    print(
                        f"  team merge (rebuild) id={team.id} "
                        f"({team.normalized_key!r} / {team.display_name!r}) "
                        f"-> id={existing.id} ({new_key!r})"
                    )
                    if not dry_run:
                        await merge_team_into(session, existing, team)
                    fixed += 1
                    continue

            changed = False
            if team.normalized_key != new_key:
                team.aliases = merge_alias_text(team.aliases, team.normalized_key)
                team.normalized_key = new_key
                changed = True
            if team.display_name != new_display:
                team.aliases = merge_alias_text(team.aliases, team.display_name)
                team.display_name = new_display
                changed = True
            if sport and not team.sport:
                team.sport = sport
                changed = True
            for c in candidates:
                if c and c != new_display and c != new_key:
                    before = team.aliases
                    team.aliases = merge_alias_text(team.aliases, c)
                    if team.aliases != before:
                        changed = True
            if changed:
                fixed += 1
                print(
                    f"  team fix id={team.id} key={new_key!r} display={new_display!r}"
                )

    if not dry_run:
        await session.flush()
    return fixed


async def _relink_match_teams(session: AsyncSession, matches: list[Match]) -> int:
    """Привязать team_home_id / team_away_id через актуальный get_or_create_team."""
    n = 0
    for m in matches:
        if m.team_home:
            home = await get_or_create_team(session, m.team_home, sport=m.sport)
            if m.team_home_id != home.id:
                m.team_home_id = home.id
                n += 1
        if m.team_away:
            away = await get_or_create_team(session, m.team_away, sport=m.sport)
            if m.team_away_id != away.id:
                m.team_away_id = away.id
                n += 1
    return n


async def _dedupe_teams_loop(
    session: AsyncSession,
    matches: list[Match],
    *,
    dry_run: bool,
    max_passes: int = 5,
) -> int:
    """Несколько проходов dedupe (после смены ключей могут всплыть новые группы)."""
    labels, sports = _match_team_context(matches)
    total = 0
    for pass_no in range(1, max_passes + 1):
        removed = await dedupe_teams(
            session,
            dry_run=dry_run,
            match_labels=labels,
            match_sports=sports,
        )
        if removed == 0:
            break
        print(f"  dedupe pass {pass_no}: merged {removed} teams")
        total += removed
        if dry_run:
            break
        matches = list(await session.scalars(select(Match)))
        labels, sports = _match_team_context(matches)
    return total


async def run_repair_catalog(*, dry_run: bool = False) -> dict[str, int]:
    """
    Полная миграция справочника:
    1. Нормализация подписей в матчах
    2. Пересчёт key/display у всех teams
    3. Слияние дубликатов teams (несколько проходов)
    4. Перепривязка team_*_id в матчах
    5. Повторный rebuild + dedupe
    6. Слияние дубликатов matches
    """
    async with async_session_factory() as session:
        try:
            matches = list(await session.scalars(select(Match)))

            labels_fixed = await _fix_match_labels(session)
            print(f"==> match labels fixed: {labels_fixed}")

            print("==> dedupe teams (pass 1)")
            teams_removed = await _dedupe_teams_loop(
                session, matches, dry_run=dry_run
            )
            if not dry_run:
                await session.flush()
                matches = list(await session.scalars(select(Match)))

            teams_rebuilt = await _rebuild_all_teams(
                session, matches, dry_run=dry_run
            )
            print(f"==> teams rebuilt: {teams_rebuilt}")

            print("==> dedupe teams (pass 2)")
            teams_removed_2 = await _dedupe_teams_loop(
                session, matches, dry_run=dry_run
            )

            if dry_run:
                matches_merged = await dedupe_matches(session, dry_run=True)
                return {
                    "match_labels_fixed": labels_fixed,
                    "teams_rebuilt": teams_rebuilt,
                    "teams_removed": teams_removed + teams_removed_2,
                    "matches_merged": matches_merged,
                }

            matches = list(await session.scalars(select(Match)))
            relinked = await _relink_match_teams(session, matches)
            print(f"==> match team links updated: {relinked}")

            matches = list(await session.scalars(select(Match)))
            teams_rebuilt_2 = await _rebuild_all_teams(session, matches)
            print(f"==> teams rebuilt (pass 2): {teams_rebuilt_2}")

            print("==> dedupe teams (pass 3)")
            teams_removed_3 = await _dedupe_teams_loop(
                session, matches, dry_run=False
            )

            labels_fixed_2 = await _fix_match_labels(session)
            matches_merged = await dedupe_matches(session, dry_run=False)
            await session.commit()

            return {
                "match_labels_fixed": labels_fixed + labels_fixed_2,
                "teams_rebuilt": teams_rebuilt + teams_rebuilt_2,
                "teams_removed": teams_removed + teams_removed_2 + teams_removed_3,
                "match_links_updated": relinked,
                "matches_merged": matches_merged,
            }
        except Exception:
            await session.rollback()
            raise
        finally:
            if dry_run:
                await session.rollback()
