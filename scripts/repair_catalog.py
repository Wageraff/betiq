#!/usr/bin/env python3
"""Починить справочник команд и слить дубликаты матчей (после git pull).

  cd /opt/betiq && export PYTHONPATH=/opt/betiq
  ./venv/bin/python3.11 scripts/repair_catalog.py
  ./venv/bin/python3.11 scripts/repair_catalog.py --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.config import setup_logging
from src.db.repair_catalog import run_repair_catalog


async def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("==> repair catalog")
    stats = await run_repair_catalog(dry_run=args.dry_run)
    print(f"Done: {stats}" + (" (dry-run)" if args.dry_run else ""))


if __name__ == "__main__":
    asyncio.run(main())
