"""Сохранение коэффициентов и истории движения линий."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Match, MatchOdds, OddsHistory

log = logging.getLogger("odds_sync")

MOVEMENT_THRESHOLD_PCT = 5.0
SIGNIFICANT_THRESHOLD_PCT = 10.0

THE_ODDS_API_MARKET_KEYS = frozenset(
    {
        "h2h",
        "spreads",
        "totals",
        "outrights",
        "btts",
        "draw_no_bet",
        "h2h_3_way",
        "h2h_lay",
        "outrights_lay",
        "team_totals",
        "alternate_team_totals",
        "double_chance",
    }
)


def _odds_outcome_label(value: object) -> str:
    if value is None:
        return "?"
    if isinstance(value, str):
        return value.strip() or "?"
    return str(value).strip() or "?"


def odds_provider_for_market(market: str) -> str:
    """Источник строки в match_odds по ключу/названию рынка."""
    key = (market or "").strip().lower().replace(" ", "_")
    if (
        key in THE_ODDS_API_MARKET_KEYS
        or key.startswith(("alternate_", "player_", "batter_"))
    ):
        return "the_odds_api"
    return "api_football"


async def _get_current_odds(
    session: AsyncSession,
    match_id: int,
    bookmaker: str,
    market: str,
    outcome: str,
    *,
    is_live: bool = False,
) -> MatchOdds | None:
    return await session.scalar(
        select(MatchOdds).where(
            MatchOdds.match_id == match_id,
            MatchOdds.bookmaker == bookmaker,
            MatchOdds.market == market,
            MatchOdds.outcome == outcome,
            MatchOdds.is_live.is_(is_live),
        )
    )


async def upsert_match_odds(
    session: AsyncSession,
    match_id: int,
    *,
    sport: str,
    bookmaker: str,
    market: str,
    outcome: str,
    odds: Decimal | float,
    point: Decimal | float | None = None,
    is_live: bool = False,
) -> None:
    new_odds = Decimal(str(odds))
    prev = await _get_current_odds(
        session, match_id, bookmaker, market, outcome, is_live=is_live
    )

    if prev is None:
        session.add(
            MatchOdds(
                match_id=match_id,
                sport=sport,
                bookmaker=bookmaker,
                market=market,
                outcome=outcome,
                odds=new_odds,
                point=Decimal(str(point)) if point is not None else None,
                is_live=is_live,
            )
        )
        return

    if prev.odds == new_odds:
        return

    old = float(prev.odds)
    movement = (float(new_odds) - old) / old * 100 if old else 0.0
    if abs(movement) >= MOVEMENT_THRESHOLD_PCT:
        session.add(
            OddsHistory(
                match_id=match_id,
                bookmaker=bookmaker,
                market=market,
                outcome=outcome,
                odds_prev=prev.odds,
                odds_curr=new_odds,
                movement_pct=Decimal(str(round(movement, 2))),
                direction="DOWN" if movement < 0 else "UP",
                is_significant=abs(movement) >= SIGNIFICANT_THRESHOLD_PCT,
            )
        )

    prev.odds = new_odds
    if point is not None:
        prev.point = Decimal(str(point))
    prev.recorded_at = datetime.now(timezone.utc)


async def ingest_odds_api_event(
    session: AsyncSession, match: Match, event: dict
) -> int:
    """Разобрать ответ The Odds API для одного event."""
    count = 0
    sport = match.sport or "unknown"
    for bookmaker in event.get("bookmakers") or []:
        bk = bookmaker.get("key") or bookmaker.get("title") or "unknown"
        for mkt in bookmaker.get("markets") or []:
            market = mkt.get("key") or "unknown"
            for out in mkt.get("outcomes") or []:
                name = out.get("name") or "?"
                price = out.get("price")
                if price is None:
                    continue
                await upsert_match_odds(
                    session,
                    match.id,
                    sport=sport,
                    bookmaker=bk,
                    market=market,
                    outcome=name,
                    odds=price,
                    point=out.get("point"),
                )
                count += 1
    match.odds_fetched_at = datetime.now(timezone.utc)
    return count


async def ingest_api_football_odds(
    session: AsyncSession, match: Match, odds_payload: dict
) -> int:
    """Разобрать ответ API-Football GET /odds для одного fixture."""
    count = 0
    sport = match.sport or "football"
    for bookmaker in odds_payload.get("bookmakers") or []:
        bk = (bookmaker.get("name") or str(bookmaker.get("id") or "unknown")).strip()
        for bet in bookmaker.get("bets") or []:
            market = (bet.get("name") or "unknown").strip()
            for val in bet.get("values") or []:
                outcome = _odds_outcome_label(val.get("value"))
                price = val.get("odd")
                if price is None:
                    continue
                await upsert_match_odds(
                    session,
                    match.id,
                    sport=sport,
                    bookmaker=bk,
                    market=market,
                    outcome=outcome,
                    odds=price,
                )
                count += 1
    if count:
        match.odds_fetched_at = datetime.now(timezone.utc)
    return count
