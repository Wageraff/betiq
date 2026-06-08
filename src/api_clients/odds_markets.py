"""Разрешённые рынки odds: config.ini, override лиги, фильтрация при ingest."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from src.config import settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.db.models import Match

# The Odds API key → API-Football bet name
TOA_TO_AF_MARKET: dict[str, str] = {
    "h2h": "Match Winner",
    "totals": "Goals Over/Under",
    "spreads": "Asian Handicap",
    "btts": "Both Teams Score",
    "draw_no_bet": "Draw No Bet",
    "double_chance": "Double Chance",
}


def _parse_csv(raw: str) -> list[str]:
    return [m.strip() for m in (raw or "").split(",") if m.strip()]


def _parse_competition_markets(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return _parse_csv(raw) or None
    if isinstance(data, list):
        out = [str(x).strip() for x in data if str(x).strip()]
        return out or None
    return None


def allowed_the_odds_api_markets(*, override: list[str] | None = None) -> frozenset[str]:
    if override:
        return frozenset(m.lower() for m in override)
    bulk = _parse_csv(settings.the_odds_api_markets)
    event = _parse_csv(settings.the_odds_api_event_markets)
    return frozenset(m.lower() for m in bulk + event)


def allowed_api_football_markets(*, override: list[str] | None = None) -> frozenset[str]:
    if override:
        names: set[str] = set()
        for m in override:
            key = m.strip().lower()
            names.add(TOA_TO_AF_MARKET.get(key, m.strip()))
        return frozenset(names)

    explicit = _parse_csv(getattr(settings, "api_football_odds_markets", "") or "")
    if explicit:
        return frozenset(explicit)

    derived: set[str] = set()
    for key in allowed_the_odds_api_markets():
        if key in TOA_TO_AF_MARKET:
            derived.add(TOA_TO_AF_MARKET[key])
    return frozenset(derived)


def is_allowed_the_odds_market(market: str, allowed: frozenset[str]) -> bool:
    return (market or "").strip().lower() in allowed


def is_allowed_api_football_market(market: str, allowed: frozenset[str]) -> bool:
    return (market or "").strip() in allowed


async def market_overrides_for_match(
    session: AsyncSession, match: Match
) -> list[str] | None:
    if not match.competition_id:
        return None
    from src.db.models import Competition

    comp = await session.get(Competition, match.competition_id)
    if not comp:
        return None
    return _parse_competition_markets(comp.odds_markets)
