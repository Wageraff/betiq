"""Авто-линковка matches ↔ API-Football / The Odds API."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.api_clients.api_football import ApiFootballClient
from src.api_clients.constants import (
    API_FOOTBALL_SPORTS,
    PROVIDER_API_FOOTBALL,
    PROVIDER_THE_ODDS_API,
)
from src.api_clients.odds_keys import odds_sport_keys_for_match
from src.api_clients.external_ids import (
    get_team_external_id,
    save_match_external_id,
    save_team_external_id,
    sync_team_logo_from_api,
)
from src.api_clients.matching import event_matches_teams
from src.api_clients.the_odds_api import TheOddsApiClient
from src.db.models import Match

log = logging.getLogger("linker")


def _parse_commence(iso: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _apply_fixture_fields(match: Match, fixture: dict) -> None:
    fix = fixture.get("fixture") or {}
    league = fixture.get("league") or {}
    teams = fixture.get("teams") or {}
    goals = fixture.get("goals") or {}
    score = fixture.get("score") or {}
    ht = score.get("halftime") or {}

    match.status = (fix.get("status") or {}).get("short") or match.status
    venue = fix.get("venue") or {}
    match.venue_name = venue.get("name") or match.venue_name
    match.venue_city = venue.get("city") or match.venue_city
    match.season = str(league.get("season") or "") or match.season
    match.round = league.get("round") or match.round
    if goals.get("home") is not None:
        match.score_home = goals.get("home")
    if goals.get("away") is not None:
        match.score_away = goals.get("away")
    if ht.get("home") is not None:
        match.score_ht_home = ht.get("home")
    if ht.get("away") is not None:
        match.score_ht_away = ht.get("away")

    for side, key in (("home", "team_home_id"), ("away", "team_away_id")):
        tdata = teams.get(side) or {}
        tid = getattr(match, key)
        logo = tdata.get("logo")
        if tid and logo:
            # sync in caller with session
            pass


async def link_match_to_api_football(
    session: AsyncSession,
    match: Match,
    *,
    client: ApiFootballClient | None = None,
    fixtures_by_date: dict[str, list[dict]] | None = None,
) -> bool:
    if match.sport not in API_FOOTBALL_SPORTS or not match.match_date:
        return False
    client = client or ApiFootballClient()
    if not client.enabled:
        return False

    home_ext = await get_team_external_id(session, match.team_home_id, PROVIDER_API_FOOTBALL)
    away_ext = await get_team_external_id(session, match.team_away_id, PROVIDER_API_FOOTBALL)
    day = match.match_date.date().isoformat()

    fixtures: list[dict] = []
    if home_ext and away_ext:
        fixtures = await client.get_fixtures(date=day, team=int(home_ext))
        for f in fixtures:
            away_id = (f.get("teams") or {}).get("away", {}).get("id")
            if str(away_id) == str(away_ext):
                fid = str((f.get("fixture") or {}).get("id"))
                await save_match_external_id(
                    session, match.id, PROVIDER_API_FOOTBALL, fid,
                    confidence=1.0,
                )
                _apply_fixture_fields(match, f)
                await _save_teams_from_fixture(session, match, f)
                return True

    cache = fixtures_by_date if fixtures_by_date is not None else {}
    if day not in cache:
        cache[day] = await client.get_fixtures(date=day)
    fixtures = cache[day]
    for f in fixtures:
        th = (f.get("teams") or {}).get("home", {})
        ta = (f.get("teams") or {}).get("away", {})
        if await event_matches_teams(
            session,
            event_home=th.get("name", ""),
            event_away=ta.get("name", ""),
            home_id=match.team_home_id,
            home_name=match.team_home,
            away_id=match.team_away_id,
            away_name=match.team_away,
            sport=match.sport,
        ):
            fid = str((f.get("fixture") or {}).get("id"))
            await save_match_external_id(
                session, match.id, PROVIDER_API_FOOTBALL, fid,
                confidence=0.85,
            )
            _apply_fixture_fields(match, f)
            await _save_teams_from_fixture(session, match, f)
            return True
    return False


async def _save_teams_from_fixture(
    session: AsyncSession, match: Match, fixture: dict
) -> None:
    from sqlalchemy import select
    from src.db.models import Team

    teams = fixture.get("teams") or {}
    for side, attr in (("home", "team_home_id"), ("away", "team_away_id")):
        tdata = teams.get(side) or {}
        tid = getattr(match, attr)
        ext_id = str(tdata.get("id") or "")
        if not tid or not ext_id:
            continue
        await save_team_external_id(
            session,
            tid,
            PROVIDER_API_FOOTBALL,
            ext_id,
            external_name=tdata.get("name"),
        )
        team = await session.get(Team, tid)
        if team:
            await sync_team_logo_from_api(session, team, tdata.get("logo"))


async def link_match_to_odds_api(
    session: AsyncSession,
    match: Match,
    *,
    client: TheOddsApiClient | None = None,
    events_by_sport: dict[str, list[dict]] | None = None,
) -> bool:
    if not match.match_date or not match.sport:
        return False
    sport_keys = await odds_sport_keys_for_match(session, match)
    if not sport_keys:
        return False
    client = client or TheOddsApiClient()
    if not client.enabled:
        return False

    cache = events_by_sport if events_by_sport is not None else {}
    for sport_key in sport_keys:
        if sport_key not in cache:
            cache[sport_key] = await client.get_events(sport_key)
        for event in cache[sport_key]:
            commence = _parse_commence(event.get("commence_time", ""))
            if not commence:
                continue
            delta = abs((commence - match.match_date).total_seconds())
            if delta > 10800:
                continue
            if await event_matches_teams(
                session,
                event_home=event.get("home_team", ""),
                event_away=event.get("away_team", ""),
                home_id=match.team_home_id,
                home_name=match.team_home,
                away_id=match.team_away_id,
                away_name=match.team_away,
                sport=match.sport,
            ):
                await save_match_external_id(
                    session,
                    match.id,
                    PROVIDER_THE_ODDS_API,
                    event["id"],
                    confidence=0.9,
                )
                return True
    return False


async def link_unlinked_matches(session: AsyncSession, *, limit: int = 50) -> dict[str, int]:
    from src.api_clients.external_ids import matches_without_provider

    stats = {"api_football": 0, "the_odds_api": 0, "checked": 0}
    af = ApiFootballClient()
    odds = TheOddsApiClient()
    fixtures_by_date: dict[str, list[dict]] = {}
    events_by_sport: dict[str, list[dict]] = {}

    for provider, fn in (
        (PROVIDER_API_FOOTBALL, link_match_to_api_football),
        (PROVIDER_THE_ODDS_API, link_match_to_odds_api),
    ):
        pending = await matches_without_provider(session, provider, limit=limit)
        for match in pending:
            stats["checked"] += 1
            try:
                if provider == PROVIDER_API_FOOTBALL:
                    ok = await fn(
                        session,
                        match,
                        client=af,
                        fixtures_by_date=fixtures_by_date,
                    )
                    if ok:
                        stats["api_football"] += 1
                else:
                    ok = await fn(
                        session,
                        match,
                        client=odds,
                        events_by_sport=events_by_sport,
                    )
                    if ok:
                        stats["the_odds_api"] += 1
            except Exception:
                log.exception("Link failed match_id=%s provider=%s", match.id, provider)
        await session.commit()
    return stats
