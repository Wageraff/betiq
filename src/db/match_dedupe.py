"""Слияние дубликатов matches."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Match, Prediction
from src.scraper.utils.match_key import build_match_key, build_slug, normalize_team_name


def _day_bucket(match_date) -> date | None:
    if match_date is None:
        return None
    return match_date.date() if hasattr(match_date, "date") else match_date


def teams_key(m: Match) -> tuple[str, str] | None:
    if not m.team_home or not m.team_away:
        return None
    return (normalize_team_name(m.team_home), normalize_team_name(m.team_away))


def cluster_by_date(matches: list[Match]) -> list[list[Match]]:
    ordered = sorted(matches, key=lambda x: (_day_bucket(x.match_date) or date.min, x.id))
    clusters: list[list[Match]] = []
    for m in ordered:
        day = _day_bucket(m.match_date)
        placed = False
        for cluster in clusters:
            ref = _day_bucket(cluster[0].match_date)
            if ref and day and abs((day - ref).days) <= 1:
                cluster.append(m)
                placed = True
                break
        if not placed:
            clusters.append([m])
    return [c for c in clusters if len(c) > 1]


async def _recount(session: AsyncSession, match_id: int) -> int:
    n = await session.scalar(
        select(func.count()).select_from(Prediction).where(Prediction.match_id == match_id)
    )
    return int(n or 0)


async def merge_match_into(
    session: AsyncSession, keeper: Match, dup: Match, *, dry_run: bool
) -> None:
    print(
        f"  match merge id={dup.id} -> {keeper.id} "
        f"({dup.team_home!r} vs {dup.team_away!r}, key={dup.match_key!r})"
    )
    if dry_run:
        return

    await session.execute(
        update(Prediction).where(Prediction.match_id == dup.id).values(match_id=keeper.id)
    )
    if dup.ai_summary and not keeper.ai_summary:
        keeper.ai_summary = dup.ai_summary
        keeper.ai_top_pick = dup.ai_top_pick
        keeper.ai_confidence = dup.ai_confidence
        keeper.ai_generated_at = dup.ai_generated_at
        keeper.ai_model = dup.ai_model

    keeper.predictions_count = await _recount(session, keeper.id)
    day = _day_bucket(keeper.match_date)
    if day:
        keeper.match_key = build_match_key(keeper.team_home, keeper.team_away, day)
        keeper.slug = build_slug(keeper.team_home, keeper.team_away, day)

    await session.delete(dup)
    await session.flush()


async def dedupe_matches(session: AsyncSession, *, dry_run: bool = False) -> int:
    matches = list(await session.scalars(select(Match).order_by(Match.id)))
    by_teams: dict[tuple[str, str], list[Match]] = defaultdict(list)
    for m in matches:
        tk = teams_key(m)
        if tk:
            by_teams[tk].append(m)

    merged = 0
    for team_matches in by_teams.values():
        for cluster in cluster_by_date(team_matches):
            print(
                f"Duplicate {teams_key(cluster[0])} — ids {[m.id for m in cluster]}"
            )
            cluster.sort(key=lambda x: x.id)
            keeper, *dups = cluster
            for dup in dups:
                await merge_match_into(session, keeper, dup, dry_run=dry_run)
                merged += 1
    return merged
