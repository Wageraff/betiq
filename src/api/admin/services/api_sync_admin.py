"""Статус и запуск синхронизации внешних API из админки."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api_clients.api_football import ApiFootballClient
from src.api_clients.the_odds_api import TheOddsApiClient
from src.config import settings
from src.db.models import (
    Competition,
    MatchExternalId,
    MatchLineup,
    MatchOdds,
    MatchStats,
    OddsHistory,
    TeamForm,
)


async def fetch_live_quotas() -> dict:
    af = ApiFootballClient()
    odds = TheOddsApiClient()

    af_status: dict = {}
    if af.enabled:
        try:
            raw = await af.get_account_status()
            req = raw.get("requests") or {}
            af_status = {
                "configured": True,
                "requests_today": req.get("current"),
                "limit_day": req.get("limit_day"),
                "subscription": (raw.get("subscription") or {}).get("plan"),
            }
        except Exception as exc:
            af_status = {"configured": True, "error": str(exc)}
    else:
        af_status = {"configured": False}

    odds_quota: dict = {}
    if odds.enabled:
        try:
            q = await odds.get_quota()
            odds_quota = {
                "configured": True,
                "remaining": q.get("remaining"),
                "used": q.get("used"),
            }
        except Exception as exc:
            odds_quota = {"configured": True, "error": str(exc)}
    else:
        odds_quota = {"configured": False}

    return {
        "api_sync_enabled": settings.api_sync_enabled,
        "api_football": af_status,
        "the_odds_api": odds_quota,
    }


async def fetch_db_counts(session: AsyncSession) -> dict[str, int]:
    async def _count(model) -> int:
        return int(await session.scalar(select(func.count()).select_from(model)) or 0)

    af_links = int(
        await session.scalar(
            select(func.count()).select_from(MatchExternalId).where(
                MatchExternalId.provider == "api_football"
            )
        )
        or 0
    )
    odds_links = int(
        await session.scalar(
            select(func.count()).select_from(MatchExternalId).where(
                MatchExternalId.provider == "the_odds_api"
            )
        )
        or 0
    )
    return {
        "competitions": await _count(Competition),
        "match_links_api_football": af_links,
        "match_links_the_odds_api": odds_links,
        "match_odds": await _count(MatchOdds),
        "odds_history": await _count(OddsHistory),
        "match_stats": await _count(MatchStats),
        "team_form": await _count(TeamForm),
        "match_lineups": await _count(MatchLineup),
    }
