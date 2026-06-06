"""Админка: управление лигами и синхронизацией."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.admin.services.api_sync_admin import fetch_live_quotas
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
    page: int = 1,
    limit: int = 50,
) -> tuple[list[dict], int]:
    since, until = upcoming_match_window()
    stmt = select(Competition)
    count_stmt = select(func.count()).select_from(Competition)
    if sport:
        stmt = stmt.where(Competition.sport == sport)
        count_stmt = count_stmt.where(Competition.sport == sport)
    if is_tracked is not None:
        stmt = stmt.where(Competition.is_tracked.is_(is_tracked))
        count_stmt = count_stmt.where(Competition.is_tracked.is_(is_tracked))

    total = int(await session.scalar(count_stmt) or 0)
    comps = (
        await session.scalars(
            stmt.order_by(Competition.name.asc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
    ).all()

    comp_ids = [c.id for c in comps]
    match_counts: dict[int, int] = {}
    if comp_ids:
        rows = (
            await session.execute(
                select(Match.competition_id, func.count())
                .where(
                    Match.competition_id.in_(comp_ids),
                    Match.match_date.isnot(None),
                    Match.match_date >= since,
                    Match.match_date <= until,
                )
                .group_by(Match.competition_id)
            )
        ).all()
        match_counts = {cid: int(cnt) for cid, cnt in rows if cid}

    items = []
    for c in comps:
        items.append(
            {
                "id": c.id,
                "name": c.name,
                "sport": c.sport,
                "country": c.country,
                "country_code": c.country_code,
                "matches_upcoming": match_counts.get(c.id, 0),
                "is_tracked": c.is_tracked,
                "sync_odds": c.sync_odds,
                "sync_stats": c.sync_stats,
                "sync_lineups": c.sync_lineups,
                "odds_markets": _parse_odds_markets(c.odds_markets),
                "odds_days_ahead": c.odds_days_ahead,
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
            select(Match).where(
                Match.competition_id == competition_id,
                Match.match_date.isnot(None),
                Match.match_date >= since,
                Match.match_date <= until,
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
