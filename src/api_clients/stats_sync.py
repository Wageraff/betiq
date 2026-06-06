"""Football: match_stats, team_form, lineups."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api_clients.api_football import ApiFootballClient
from src.api_clients.constants import PROVIDER_API_FOOTBALL
from src.api_clients.external_ids import get_match_external_id, get_team_external_id
from src.db.models import Match, MatchLineup, MatchStats, TeamForm

log = logging.getLogger("stats_sync")

_STAT_MAP = {
    "Shots on Goal": "shots_on_goal",
    "Shots off Goal": "shots_off_goal",
    "Total Shots": "shots_total",
    "Blocked Shots": "shots_blocked",
    "Shots insidebox": "shots_insidebox",
    "Shots outsidebox": "shots_outsidebox",
    "Corner Kicks": "corners",
    "Fouls": "fouls",
    "Yellow Cards": "yellow_cards",
    "Red Cards": "red_cards",
    "Offsides": "offsides",
    "Ball Possession": "possession",
    "Total passes": "passes_total",
    "Passes accurate": "passes_accurate",
    "Goalkeeper Saves": "goalkeeper_saves",
}


def _parse_pct(val: str | int | None) -> int | None:
    if val is None:
        return None
    if isinstance(val, int):
        return val
    text = str(val).replace("%", "").strip()
    try:
        return int(text)
    except ValueError:
        return None


async def fetch_post_match_stats(session: AsyncSession, match: Match) -> bool:
    if match.status != "FT" or match.stats_fetched_at is not None:
        return False
    if match.sport != "football":
        return False
    fixture_id = await get_match_external_id(session, match.id, PROVIDER_API_FOOTBALL)
    if not fixture_id:
        return False
    client = ApiFootballClient()
    if not client.enabled:
        return False

    rows = await client.get_fixture_statistics(fixture_id)
    if not rows:
        return False

    home_ext = await get_team_external_id(session, match.team_home_id, PROVIDER_API_FOOTBALL)
    away_ext = await get_team_external_id(session, match.team_away_id, PROVIDER_API_FOOTBALL)

    for block in rows:
        team_info = block.get("team") or {}
        tid = team_info.get("id")
        side = None
        if home_ext and str(tid) == str(home_ext):
            side = "home"
        elif away_ext and str(tid) == str(away_ext):
            side = "away"
        elif fuzzy_side_home(team_info, match):
            side = "home"
        elif fuzzy_side_away(team_info, match):
            side = "away"
        else:
            continue
        stats_data = {k: None for k in _STAT_MAP.values()}
        for item in block.get("statistics") or []:
            key = _STAT_MAP.get(item.get("type", ""))
            if key:
                val = item.get("value")
                stats_data[key] = _parse_pct(val) if key == "possession" else (
                    int(val) if val is not None and str(val).isdigit() else None
                )
        team_id = match.team_home_id if side == "home" else match.team_away_id
        existing = await session.scalar(
            select(MatchStats).where(
                MatchStats.match_id == match.id,
                MatchStats.side == side,
                MatchStats.half == "full",
            )
        )
        if existing:
            for k, v in stats_data.items():
                setattr(existing, k, v)
        else:
            session.add(
                MatchStats(match_id=match.id, team_id=team_id, side=side, **stats_data)
            )

    match.stats_fetched_at = datetime.now(timezone.utc)
    return True


def fuzzy_side_away(team_info: dict, match: Match) -> bool:
    from src.api_clients.fuzzy import fuzzy_match
    return fuzzy_match(team_info.get("name", ""), match.team_away)


async def fetch_team_form(session: AsyncSession, team_id: int) -> int:
    ext = await get_team_external_id(session, team_id, PROVIDER_API_FOOTBALL)
    if not ext:
        return 0
    client = ApiFootballClient()
    if not client.enabled:
        return 0
    fixtures = await client.get_fixtures(team=int(ext), last=10)
    saved = 0
    for f in fixtures:
        fid = str((f.get("fixture") or {}).get("id") or "")
        if not fid:
            continue
        exists = await session.scalar(
            select(TeamForm.id).where(
                TeamForm.team_id == team_id,
                TeamForm.fixture_external_id == fid,
            )
        )
        if exists:
            continue
        fix = f.get("fixture") or {}
        goals = f.get("goals") or {}
        teams = f.get("teams") or {}
        is_home = str((teams.get("home") or {}).get("id")) == str(ext)
        gh = goals.get("home") or 0
        ga = goals.get("away") or 0
        scored = gh if is_home else ga
        conceded = ga if is_home else gh
        if scored > conceded:
            result = "W"
        elif scored < conceded:
            result = "L"
        else:
            result = "D"
        opponent = (teams.get("away") if is_home else teams.get("home")) or {}
        raw_date = (fix.get("date") or "1970-01-01T00:00:00+00:00")[:10]
        session.add(
            TeamForm(
                team_id=team_id,
                fixture_external_id=fid,
                match_date=date.fromisoformat(raw_date),
                opponent_name=opponent.get("name"),
                is_home=is_home,
                result=result,
                goals_scored=scored,
                goals_conceded=conceded,
                competition_name=(f.get("league") or {}).get("name"),
            )
        )
        saved += 1
    return saved


async def fetch_lineups(session: AsyncSession, match: Match) -> bool:
    if match.sport != "football" or not match.match_date:
        return False
    now = datetime.now(timezone.utc)
    if match.match_date - now > timedelta(hours=2):
        return False
    fixture_id = await get_match_external_id(session, match.id, PROVIDER_API_FOOTBALL)
    if not fixture_id:
        return False
    client = ApiFootballClient()
    rows = await client.get_fixture_lineups(fixture_id)
    if not rows:
        return False
    for block in rows:
        team_info = block.get("team") or {}
        side = "home" if fuzzy_side_home(team_info, match) else "away"
        team_id = match.team_home_id if side == "home" else match.team_away_id
        players = []
        for p in block.get("startXI") or []:
            pl = p.get("player") or {}
            players.append(pl)
        for p in block.get("substitutes") or []:
            pl = p.get("player") or {}
            players.append(pl)
        existing = await session.scalar(
            select(MatchLineup).where(
                MatchLineup.match_id == match.id, MatchLineup.side == side
            )
        )
        coach = block.get("coach") or {}
        payload = {
            "formation": block.get("formation"),
            "coach_name": coach.get("name"),
            "coach_photo_url": coach.get("photo"),
            "lineup_json": players,
            "team_id": team_id,
        }
        if existing:
            for k, v in payload.items():
                setattr(existing, k, v)
        else:
            session.add(MatchLineup(match_id=match.id, side=side, **payload))
    return True


def fuzzy_side_home(team_info: dict, match: Match) -> bool:
    from src.api_clients.fuzzy import fuzzy_match
    return fuzzy_match(team_info.get("name", ""), match.team_home)


async def sync_prematch_forms(session: AsyncSession, *, hours: int = 48) -> int:
    until = datetime.now(timezone.utc) + timedelta(hours=hours)
    matches = (
        await session.scalars(
            select(Match).where(
                Match.sport == "football",
                Match.match_date.isnot(None),
                Match.match_date <= until,
                Match.match_date >= datetime.now(timezone.utc),
            )
        )
    ).all()
    total = 0
    seen: set[int] = set()
    for m in matches:
        for tid in (m.team_home_id, m.team_away_id):
            if not tid or tid in seen:
                continue
            seen.add(tid)
            total += await fetch_team_form(session, tid)
    await session.commit()
    return total


async def sync_post_match_stats(session: AsyncSession) -> int:
    matches = (
        await session.scalars(
            select(Match).where(
                Match.sport == "football",
                Match.status == "FT",
                Match.stats_fetched_at.is_(None),
            ).limit(30)
        )
    ).all()
    n = 0
    for m in matches:
        if await fetch_post_match_stats(session, m):
            n += 1
    await session.commit()
    return n


async def sync_upcoming_lineups(session: AsyncSession) -> int:
    now = datetime.now(timezone.utc)
    matches = (
        await session.scalars(
            select(Match).where(
                Match.sport == "football",
                Match.match_date.isnot(None),
                Match.match_date >= now,
                Match.match_date <= now + timedelta(hours=2),
            )
        )
    ).all()
    n = 0
    for m in matches:
        if await fetch_lineups(session, m):
            n += 1
    await session.commit()
    return n
