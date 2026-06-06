"""Админка: управление лигами и синхронизацией."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.admin.services.api_sync_admin import fetch_live_quotas
from src.api.admin.services.competition_match_link import (
    competition_search_clause,
    upcoming_match_count_scalar,
    upcoming_match_date_clause,
    match_links_competition,
)
from src.api_clients.football_odds_sync import sync_api_football_odds
from src.api_clients.odds_keys import odds_sport_keys_for_match
from src.api_clients.odds_scope import upcoming_match_window
from src.api_clients.odds_sync import sync_odds_for_sport_key
from src.api_clients.quota_log import latest_quota_snapshots, record_odds_sync
from src.db.models import Competition, Match


def _parse_odds_markets(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(x) for x in data]
    except json.JSONDecodeError:
        pass
    return None


def _serialize_odds_markets(markets: list[str] | None) -> str | None:
    if not markets:
        return None
    return json.dumps(markets)


async def list_competitions(
    session: AsyncSession,
    *,
    sport: str | None = None,
    is_tracked: bool | None = None,
    q: str | None = None,
    with_matches: bool | None = None,
    order: str = "name",
    page: int = 1,
    limit: int = 50,
) -> tuple[list[dict], int]:
    since, until = upcoming_match_window()
    match_count = upcoming_match_count_scalar(since, until)

    base = select(Competition, match_count.label("match_count"))
    count_stmt = select(func.count()).select_from(Competition)

    if sport:
        base = base.where(Competition.sport == sport)
        count_stmt = count_stmt.where(Competition.sport == sport)
    if is_tracked is not None:
        base = base.where(Competition.is_tracked.is_(is_tracked))
        count_stmt = count_stmt.where(Competition.is_tracked.is_(is_tracked))
    if q and q.strip():
        clause = competition_search_clause(q, since, until)
        base = base.where(clause)
        count_stmt = count_stmt.where(clause)
    if with_matches:
        base = base.where(match_count > 0)
        count_stmt = count_stmt.where(match_count > 0)

    total = int(await session.scalar(count_stmt) or 0)

    if order == "matches":
        base = base.order_by(match_count.desc(), Competition.name.asc())
    else:
        base = base.order_by(Competition.name.asc())

    rows = (
        await session.execute(base.offset((page - 1) * limit).limit(limit))
    ).all()

    items = []
    for comp, mcount in rows:
        items.append(
            {
                "id": comp.id,
                "name": comp.name,
                "sport": comp.sport,
                "country": comp.country,
                "country_code": comp.country_code,
                "matches_upcoming": int(mcount or 0),
                "is_tracked": comp.is_tracked,
                "sync_odds": comp.sync_odds,
                "sync_stats": comp.sync_stats,
                "sync_lineups": comp.sync_lineups,
                "odds_markets": _parse_odds_markets(comp.odds_markets),
                "odds_days_ahead": comp.odds_days_ahead,
            }
        )
    return items, total


async def update_competition(
    session: AsyncSession,
    competition_id: int,
    *,
    is_tracked: bool | None = None,
    sync_odds: bool | None = None,
    sync_stats: bool | None = None,
    sync_lineups: bool | None = None,
    odds_markets: list[str] | None = None,
    odds_days_ahead: int | None = None,
    unset_odds_days_ahead: bool = False,
) -> Competition | None:
    comp = await session.get(Competition, competition_id)
    if not comp:
        return None
    if is_tracked is not None:
        comp.is_tracked = is_tracked
        if is_tracked and sync_odds is None:
            comp.sync_odds = True
    if sync_odds is not None:
        comp.sync_odds = sync_odds
    if sync_stats is not None:
        comp.sync_stats = sync_stats
    if sync_lineups is not None:
        comp.sync_lineups = sync_lineups
    if odds_markets is not None:
        comp.odds_markets = _serialize_odds_markets(odds_markets)
    if unset_odds_days_ahead:
        comp.odds_days_ahead = None
    elif odds_days_ahead is not None:
        comp.odds_days_ahead = odds_days_ahead
    await session.commit()
    await session.refresh(comp)
    return comp


async def sync_competition_now(session: AsyncSession, competition_id: int) -> dict:
    comp = await session.get(Competition, competition_id)
    if not comp:
        return {"error": "not_found"}

    since, until = upcoming_match_window()
    if comp.odds_days_ahead:
        until = datetime.now(timezone.utc) + timedelta(days=comp.odds_days_ahead)

    matches = (
        await session.scalars(
            select(Match)
            .join(Competition, Competition.id == comp.id)
            .where(
                upcoming_match_date_clause(since, until),
                match_links_competition(),
            )
        )
    ).all()

    sport_keys: set[str] = set()
    for m in matches:
        sport_keys.update(await odds_sport_keys_for_match(session, m))

    odds_lines = 0
    for key in sorted(sport_keys):
        odds_lines += await sync_odds_for_sport_key(session, key)
        await record_odds_sync(session, key)
    await session.commit()
    af_lines = await sync_api_football_odds(session, limit=max(len(matches), 1))

    return {
        "competition_id": competition_id,
        "matches": len(matches),
        "sport_keys": sorted(sport_keys),
        "the_odds_api_lines": odds_lines,
        "api_football_lines": af_lines,
    }


async def api_quota_status(session: AsyncSession) -> dict:
    live = await fetch_live_quotas()
    snaps = await latest_quota_snapshots(session)
    toa_snap = snaps.get("the_odds_api")
    af_snap = snaps.get("api_football")
    return {
        "the_odds_api_remaining": live["the_odds_api"].get("remaining")
        or (toa_snap.requests_remaining if toa_snap else None),
        "the_odds_api_used": live["the_odds_api"].get("used")
        or (toa_snap.requests_used if toa_snap else None),
        "api_football_remaining": (
            (af_snap.requests_remaining if af_snap else None)
            or (
                (live["api_football"].get("limit_day") or 0)
                - (live["api_football"].get("requests_today") or 0)
                if live["api_football"].get("limit_day")
                else None
            )
        ),
        "api_football_limit": live["api_football"].get("limit_day"),
        "checked_at": datetime.now(timezone.utc),
    }
