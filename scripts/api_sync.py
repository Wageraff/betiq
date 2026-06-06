#!/usr/bin/env python3
"""Ручной запуск синхронизации внешних API.

Usage:
  PYTHONPATH=. python scripts/api_sync.py link
  PYTHONPATH=. python scripts/api_sync.py leagues
  PYTHONPATH=. python scripts/api_sync.py odds
  PYTHONPATH=. python scripts/api_sync.py stats
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from src.api_clients import jobs as api_jobs
from src.config import setup_logging


async def main_async(action: str) -> None:
    if action == "link":
        await api_jobs.job_link_matches()
    elif action == "leagues":
        await api_jobs.job_sync_leagues()
    elif action == "logos":
        await api_jobs.job_sync_team_logos()
    elif action == "form":
        await api_jobs.job_fetch_team_form()
    elif action == "lineups":
        await api_jobs.job_fetch_lineups()
    elif action == "odds":
        await api_jobs.job_fetch_odds()
    elif action == "stats":
        await api_jobs.job_fetch_post_match_stats()
    elif action == "cleanup":
        await api_jobs.job_cleanup_ai_cache()
    elif action == "cleanup_data":
        await api_jobs.job_cleanup_old_data()
    elif action == "reset_odds":
        await api_jobs.job_reset_odds(refetch=True)
    elif action == "reset_odds_only":
        await api_jobs.job_reset_odds(refetch=False)
    else:
        raise SystemExit(f"Unknown action: {action}")


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(description="BetIQ external API sync")
    parser.add_argument(
        "action",
        choices=[
            "link",
            "leagues",
            "logos",
            "form",
            "lineups",
            "odds",
            "stats",
            "cleanup",
            "cleanup_data",
            "reset_odds",
            "reset_odds_only",
        ],
    )
    args = parser.parse_args()
    asyncio.run(main_async(args.action))


if __name__ == "__main__":
    main()
