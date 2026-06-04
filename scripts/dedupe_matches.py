#!/usr/bin/env python3
"""Слить дубликаты matches (одинаковые нормализованные команды + дата).

Пример: id 42 «Franta» и id 49 «Franța» — один матч, разные старые match_key.

  cd /opt/betiq && PYTHONPATH=/opt/betiq ./venv/bin/python3.11 scripts/dedupe_matches.py
  ./venv/bin/python3.11 scripts/dedupe_matches.py --dry-run
  ./venv/bin/python3.11 scripts/dedupe_matches.py --ids 42,49
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import func, select, update

from src.config import setup_logging
from src.db.models import Match, Prediction
from src.db.session import async_session_factory
from src.scraper.utils.match_key import build_match_key, normalize_team_name


def _day_bucket(match_date) -> date | None:
    if match_date is None:
        return None
    return match_date.date() if hasattr(match_date, "date") else match_date


def _teams_key(m: Match) -> tuple[str, str] | None:
    if not m.team_home or not m.team_away:
        return None
    return (normalize_team_name(m.team_home), normalize_team_name(m.team_away))


def _cluster_by_date(matches: list[Match]) -> list[list[Match]]:
    """Группы с разницей даты не больше 1 дня (разный парсинг kickoff по сайтам)."""
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


async def _recount(session, match_id: int) -> int:
    n = await session.scalar(
        select(func.count()).select_from(Prediction).where(Prediction.match_id == match_id)
    )
    return int(n or 0)


async def merge_into(session, keeper: Match, dup: Match, *, dry_run: bool) -> None:
    print(
        f"  merge match_id={dup.id} -> {keeper.id} "
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
        from src.scraper.utils.match_key import build_slug

        keeper.slug = build_slug(keeper.team_home, keeper.team_away, day)

    await session.delete(dup)
    await session.flush()


async def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--ids",
        help="Слить только указанные id (через запятую), в один матч с минимальным id",
    )
    args = parser.parse_args()

    async with async_session_factory() as session:
        if args.ids:
            ids = [int(x.strip()) for x in args.ids.split(",") if x.strip()]
            rows = list(
                await session.scalars(select(Match).where(Match.id.in_(ids)).order_by(Match.id))
            )
            if len(rows) < 2:
                print("Need at least 2 match rows for --ids")
                return
            keeper, *dups = rows
            for dup in dups:
                await merge_into(session, keeper, dup, dry_run=args.dry_run)
        else:
            matches = list(await session.scalars(select(Match).order_by(Match.id)))
            by_teams: dict[tuple[str, str], list[Match]] = defaultdict(list)
            for m in matches:
                tk = _teams_key(m)
                if tk:
                    by_teams[tk].append(m)

            merged = 0
            for tk, team_matches in sorted(by_teams.items()):
                for cluster in _cluster_by_date(team_matches):
                    print(
                        f"Duplicate {tk[0]}:{tk[1]} — {len(cluster)} rows "
                        f"(ids {[m.id for m in cluster]})"
                    )
                    cluster.sort(key=lambda x: x.id)
                    keeper, *dups = cluster
                    for dup in dups:
                        await merge_into(session, keeper, dup, dry_run=args.dry_run)
                        merged += 1

            if not merged and not args.ids:
                print("No duplicate groups found.")

        if not args.dry_run:
            await session.commit()
            print("Done.")
        else:
            print("Dry run — no DB changes.")


if __name__ == "__main__":
    asyncio.run(main())
