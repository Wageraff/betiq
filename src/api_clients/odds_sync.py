"""Bulk fetch odds from The Odds API."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api_clients.constants import PROVIDER_THE_ODDS_API, sport_for_odds_key
from src.api_clients.quota_log import get_last_odds_sync, record_odds_sync
from src.config import settings
from src.api_clients.external_ids import delete_match_external_id, save_match_external_id
from src.api_clients.matching import event_matches_teams
from src.api_clients.odds import ingest_odds_api_event
from src.api_clients.odds_keys import odds_sport_keys_for_match
from src.api_clients.odds_scope import (
    sport_keys_for_odds_sync,
    upcoming_matches,
)
from src.api_clients.the_odds_api import TheOddsApiClient
from src.db.models import Match, MatchExternalId

log = logging.getLogger("odds_sync")


def _parse_commence(iso: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


async def _match_by_odds_event_id(session: AsyncSession, event_id: str) -> Match | None:
    row = await session.scalar(
        select(MatchExternalId).where(
            MatchExternalId.provider == PROVIDER_THE_ODDS_API,
            MatchExternalId.external_id == event_id,
        )
    )
    if not row:
        return None
    return await session.get(Match, row.match_id)


async def _match_by_fuzzy(
    session: AsyncSession,
    *,
    sport: str,
    home: str,
    away: str,
    commence: datetime | None,
) -> Match | None:
    stmt = select(Match).where(Match.sport == sport)
    if commence is not None:
        window = timedelta(hours=3)
        stmt = stmt.where(
            Match.match_date >= commence - window,
            Match.match_date <= commence + window,
        )
    candidates = (await session.scalars(stmt)).all()
    for m in candidates:
        if await event_matches_teams(
            session,
            event_home=home,
            event_away=away,
            home_id=m.team_home_id,
            home_name=m.team_home,
            away_id=m.team_away_id,
            away_name=m.team_away,
            sport=m.sport,
        ):
            return m
    return None


async def sync_odds_for_sport_key(session: AsyncSession, sport_key: str) -> int:
    client = TheOddsApiClient()
    if not client.enabled:
        return 0
    events = await client.get_odds(sport_key)
    sport = sport_for_odds_key(sport_key)
    count = 0
    for event in events:
        event_id = event.get("id", "")
        match = await _match_by_odds_event_id(session, event_id)
        if not match:
            commence = _parse_commence(event.get("commence_time", ""))
            match = await _match_by_fuzzy(
                session,
                sport=sport,
                home=event.get("home_team", ""),
                away=event.get("away_team", ""),
                commence=commence,
            )
            if match and event_id:
                await save_match_external_id(
                    session,
                    match.id,
                    PROVIDER_THE_ODDS_API,
                    event_id,
                    confidence=0.85,
                )
        if match:
            count += await ingest_odds_api_event(session, match, event)
    await session.commit()
    return count


async def sync_linked_event_odds(
    session: AsyncSession,
    *,
    sports: set[str] | None = None,
) -> int:
    """btts / alternate_* — per-event; только football (рынки soccer-specific)."""
    if not settings.the_odds_api_event_markets.strip():
        return 0
    client = TheOddsApiClient()
    if not client.enabled:
        return 0

    event_sports = sports if sports else {"football"}
    if "football" not in event_sports:
        return 0

    upcoming_ids = {
        m.id
        for m in await upcoming_matches(session, sports={"football"}, for_odds_sync=True)
    }
    if not upcoming_ids:
        return 0
    stmt = (
        select(Match, MatchExternalId.external_id)
        .join(MatchExternalId, MatchExternalId.match_id == Match.id)
        .where(
            MatchExternalId.provider == PROVIDER_THE_ODDS_API,
            Match.id.in_(upcoming_ids),
            Match.sport == "football",
        )
        .order_by(Match.match_date.asc())
        .limit(settings.the_odds_api_event_batch_size)
    )
    rows = (await session.execute(stmt)).all()

    total = 0
    for match, event_id in rows:
        if not event_id:
            continue
        try:
            sport_keys = await odds_sport_keys_for_match(session, match)
            if not sport_keys:
                continue
            statuses: list[int | None] = []
            got_odds = False
            for sport_key in sport_keys:
                event, status = await client.get_event_odds_with_status(
                    sport_key, event_id
                )
                statuses.append(status)
                if event and event.get("bookmakers"):
                    total += await ingest_odds_api_event(session, match, event)
                    got_odds = True
                    break
            if (
                not got_odds
                and statuses
                and all(s == 404 for s in statuses)
            ):
                if await delete_match_external_id(
                    session, match.id, PROVIDER_THE_ODDS_API
                ):
                    log.info(
                        "Removed stale the_odds_api link match_id=%s event_id=%s",
                        match.id,
                        event_id,
                    )
        except Exception:
            await session.rollback()
            log.exception("Event odds failed match_id=%s", match.id)
    await session.commit()
    log.info("The Odds API event odds: %s lines for %s matches", total, len(rows))
    return total


async def sync_all_odds(
    session: AsyncSession,
    *,
    sports: set[str] | None = None,
    force: bool = False,
) -> int:
    """The Odds API bulk (+ event-odds для football). sports=None → все поддерживаемые."""
    keys = await sport_keys_for_odds_sync(session, sports=sports)
    upcoming = await upcoming_matches(session, sports=sports, for_odds_sync=True)
    log.info(
        "Odds sync mode=%s sports=%s keys=%s upcoming_matches=%s force=%s",
        settings.odds_sync_mode,
        sorted(sports) if sports else "all",
        keys,
        len(upcoming),
        force,
    )
    min_interval = settings.odds_min_interval_minutes * 60
    now = datetime.now(timezone.utc)
    total = 0
    for key in keys:
        if not force:
            last = await get_last_odds_sync(session, key)
            if last and (now - last).total_seconds() < min_interval:
                log.debug("Skip odds sync %s, last=%s", key, last)
                continue
        try:
            n = await sync_odds_for_sport_key(session, key)
            total += n
            await record_odds_sync(session, key)
            await session.commit()
        except Exception:
            await session.rollback()
            log.exception("Odds sync failed for %s", key)
    if sports is None or "football" in sports:
        try:
            total += await sync_linked_event_odds(session, sports=sports)
        except Exception:
            log.exception("Event odds sync failed")
    return total
