#!/usr/bin/env python3
"""Слить дубликаты matches (одинаковые нормализованные команды + дата).

  cd /opt/betiq && PYTHONPATH=/opt/betiq ./venv/bin/python3.11 scripts/dedupe_matches.py
  ./venv/bin/python3.11 scripts/dedupe_matches.py --dry-run
  ./venv/bin/python3.11 scripts/dedupe_matches.py --ids 42,49

Полный ремонт (команды + матчи): scripts/repair_catalog.py
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import select

from src.config import setup_logging
from src.db.match_dedupe import dedupe_matches, merge_match_into
from src.db.models import Match
from src.db.session import async_session_factory


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
                await merge_match_into(session, keeper, dup, dry_run=args.dry_run)
        else:
            merged = await dedupe_matches(session, dry_run=args.dry_run)
            if not merged:
                print("No duplicate groups found.")

        if not args.dry_run:
            await session.commit()
            print("Done.")
        else:
            print("Dry run — no DB changes.")


if __name__ == "__main__":
    asyncio.run(main())
