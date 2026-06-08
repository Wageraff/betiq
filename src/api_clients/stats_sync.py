"""Football: match_stats, team_form, lineups, injuries, h2h, api_predictions."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api_clients.api_football import ApiFootballClient
from src.api_clients.constants import PROVIDER_API_FOOTBALL
from src.api_clients.external_ids import get_match_external_id, get_team_external_id
from src.api_clients.odds_scope import _competition_sync_clause, upcoming_matches
from src.db.models import (
    Competition,
    Match,
    MatchApiPrediction,
    MatchExternalId,
    MatchH2H,
    MatchInjury,
    MatchLineup,
    MatchStats,
    TeamForm,
)

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


async def _linked_football_match_ids(session: AsyncSession) -> set[int]:
    rows = await session.scalars(
        select(MatchExternalId.match_id).where(
            MatchExternalId.provider == PROVIDER_API_FOOTBALL
        )
    )
    return set(rows.all())


async def sync_prematch_forms(session: AsyncSession, *, hours: int = 48) -> int:
    until = datetime.now(timezone.utc) + timedelta(hours=hours)
    now = datetime.now(timezone.utc)
    linked = await _linked_football_match_ids(session)
    matches = [
        m
        for m in await upcoming_matches(session, sports={"football"}, for_stats_sync=True)
        if m.id in linked and m.match_date and now <= m.match_date <= until
    ]
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
    linked = await _linked_football_match_ids(session)
    if not linked:
        return 0
    matches = (
        await session.scalars(
            select(Match)
            .join(Competition, Match.competition_id == Competition.id, isouter=True)
            .where(
                Match.sport == "football",
                Match.status == "FT",
                Match.stats_fetched_at.is_(None),
                Match.id.in_(linked),
                _competition_sync_clause("sync_stats"),
            )
            .limit(30)
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
    linked = await _linked_football_match_ids(session)
    matches = [
        m
        for m in await upcoming_matches(session, sports={"football"}, for_lineups_sync=True)
        if m.id in linked
        and m.match_date
        and now <= m.match_date <= now + timedelta(hours=2)
    ]
    n = 0
    for m in matches:
        if await fetch_lineups(session, m):
            n += 1
    await session.commit()
    return n


# ---------------------------------------------------------------------------
# Injuries
# ---------------------------------------------------------------------------

async def fetch_injuries(session: AsyncSession, match: Match) -> bool:
    """Загрузить травмы/дисквалификации для матча. Запрашивать за 48ч до kickoff."""
    if match.sport != "football" or match.injuries_fetched_at is not None:
        return False
    fixture_id = await get_match_external_id(session, match.id, PROVIDER_API_FOOTBALL)
    if not fixture_id:
        return False
    client = ApiFootballClient()
    if not client.enabled:
        return False

    rows = await client.get_fixture_injuries(fixture_id)
    if not rows:
        match.injuries_fetched_at = datetime.now(timezone.utc)
        return False

    home_ext = await get_team_external_id(session, match.team_home_id, PROVIDER_API_FOOTBALL)
    away_ext = await get_team_external_id(session, match.team_away_id, PROVIDER_API_FOOTBALL)

    # Удалить старые записи перед перезаписью
    await session.execute(
        delete(MatchInjury).where(MatchInjury.match_id == match.id)
    )

    for row in rows:
        player = row.get("player") or {}
        team = row.get("team") or {}
        team_ext_id = str(team.get("id") or "")
        side = None
        if home_ext and team_ext_id == str(home_ext):
            side = "home"
        elif away_ext and team_ext_id == str(away_ext):
            side = "away"
        elif fuzzy_side_home(team, match):
            side = "home"
        elif fuzzy_side_away(team, match):
            side = "away"

        player_name = player.get("name") or ""
        if not player_name:
            continue

        session.add(
            MatchInjury(
                match_id=match.id,
                team_id=match.team_home_id if side == "home" else (
                    match.team_away_id if side == "away" else None
                ),
                team_name=team.get("name"),
                side=side,
                player_name=player_name,
                player_id_ext=str(player.get("id") or "") or None,
                position=player.get("type"),
                injury_type=player.get("reason"),
                reason=row.get("reason"),
            )
        )

    match.injuries_fetched_at = datetime.now(timezone.utc)
    return True


async def sync_prematch_injuries(session: AsyncSession, *, hours: int = 48) -> int:
    """Загружать травмы для матчей в ближайшие N часов."""
    until = datetime.now(timezone.utc) + timedelta(hours=hours)
    now = datetime.now(timezone.utc)
    linked = await _linked_football_match_ids(session)
    matches = [
        m
        for m in await upcoming_matches(session, sports={"football"}, for_stats_sync=True)
        if m.id in linked
        and m.match_date
        and now <= m.match_date <= until
        and m.injuries_fetched_at is None
    ]
    n = 0
    for m in matches:
        if await fetch_injuries(session, m):
            n += 1
    await session.commit()
    return n


# ---------------------------------------------------------------------------
# H2H
# ---------------------------------------------------------------------------

async def fetch_h2h(session: AsyncSession, match: Match) -> bool:
    """Загрузить последние 10 очных встреч. Запрашивать однократно при линковке."""
    if match.sport != "football" or match.h2h_fetched_at is not None:
        return False
    home_ext = await get_team_external_id(session, match.team_home_id, PROVIDER_API_FOOTBALL)
    away_ext = await get_team_external_id(session, match.team_away_id, PROVIDER_API_FOOTBALL)
    if not home_ext or not away_ext:
        return False
    client = ApiFootballClient()
    if not client.enabled:
        return False

    fixtures = await client.get_headtohead(home_ext, away_ext, last=10)
    if not fixtures:
        match.h2h_fetched_at = datetime.now(timezone.utc)
        return False

    for f in fixtures:
        fix = f.get("fixture") or {}
        fid = str(fix.get("id") or "")
        if not fid:
            continue
        teams = f.get("teams") or {}
        goals = f.get("goals") or {}
        raw_date = (fix.get("date") or "")[:10] or None

        existing = await session.scalar(
            select(MatchH2H).where(
                MatchH2H.match_id == match.id,
                MatchH2H.fixture_external_id == fid,
            )
        )
        if existing:
            continue

        session.add(
            MatchH2H(
                match_id=match.id,
                fixture_external_id=fid,
                match_date=date.fromisoformat(raw_date) if raw_date else None,
                home_team=(teams.get("home") or {}).get("name"),
                away_team=(teams.get("away") or {}).get("name"),
                score_home=goals.get("home"),
                score_away=goals.get("away"),
                competition_name=(f.get("league") or {}).get("name"),
                status=(fix.get("status") or {}).get("short"),
            )
        )

    match.h2h_fetched_at = datetime.now(timezone.utc)
    return True


async def sync_prematch_h2h(session: AsyncSession, *, hours: int = 72) -> int:
    """Загружать H2H для матчей в ближайшие N часов (однократно)."""
    until = datetime.now(timezone.utc) + timedelta(hours=hours)
    now = datetime.now(timezone.utc)
    linked = await _linked_football_match_ids(session)
    matches = [
        m
        for m in await upcoming_matches(session, sports={"football"}, for_stats_sync=True)
        if m.id in linked
        and m.match_date
        and now <= m.match_date <= until
        and m.h2h_fetched_at is None
    ]
    n = 0
    for m in matches:
        if await fetch_h2h(session, m):
            n += 1
    await session.commit()
    return n


# ---------------------------------------------------------------------------
# API-Football Predictions (/predictions)
# ---------------------------------------------------------------------------

_FORM_LAST_N = 10


def _normalize_form(val: object | None) -> str | None:
    """API отдаёт длинную строку W/D/L — храним последние N результатов."""
    if val is None:
        return None
    text = str(val).strip().upper()
    if not text:
        return None
    letters = "".join(c for c in text if c in "WDL")
    if letters:
        return letters[-_FORM_LAST_N:]
    return text[:_FORM_LAST_N]


async def fetch_api_prediction(
    session: AsyncSession, match: Match, *, force: bool = False
) -> bool:
    """Загрузить встроенный прогноз API-Football (вероятности, форма, совет)."""
    if match.sport != "football":
        return False
    fixture_id = await get_match_external_id(session, match.id, PROVIDER_API_FOOTBALL)
    if not fixture_id:
        return False

    existing = await session.scalar(
        select(MatchApiPrediction).where(MatchApiPrediction.match_id == match.id)
    )
    if existing and not force:
        return False

    client = ApiFootballClient()
    if not client.enabled:
        return False

    rows = await client.get_fixture_predictions(fixture_id)
    if not rows:
        # Не ставим api_prediction_fetched_at — повторим при следующем odds-sync
        log.info(
            "API-Football prediction empty fixture=%s match_id=%s",
            fixture_id,
            match.id,
        )
        return False

    data = rows[0]
    pred = data.get("predictions") or {}
    winner = pred.get("winner") or {}
    percent = pred.get("percent") or {}
    teams = data.get("teams") or {}
    home_team = teams.get("home") or {}
    away_team = teams.get("away") or {}
    goals = pred.get("goals") if isinstance(pred.get("goals"), dict) else {}

    payload = dict(
        winner_team=winner.get("name"),
        winner_comment=winner.get("comment"),
        percent_home=_parse_pct(percent.get("home")),
        percent_draw=_parse_pct(percent.get("draw")),
        percent_away=_parse_pct(percent.get("away")),
        goals_home=str(goals.get("home") or "") or None,
        goals_away=str(goals.get("away") or "") or None,
        advice=pred.get("advice"),
        form_home=_normalize_form((home_team.get("league") or {}).get("form")),
        form_away=_normalize_form((away_team.get("league") or {}).get("form")),
        raw_json=data,
    )
    if existing:
        for k, v in payload.items():
            setattr(existing, k, v)
        existing.fetched_at = datetime.now(timezone.utc)
    else:
        session.add(MatchApiPrediction(match_id=match.id, **payload))

    match.api_prediction_fetched_at = datetime.now(timezone.utc)
    return True


async def matches_pending_api_predictions(
    session: AsyncSession, *, limit: int | None = None
) -> list[Match]:
    """Предстоящие AF-матчи без сохранённого /predictions (то же окно, что odds)."""
    from src.api_clients.odds_scope import upcoming_football_matches

    linked = await _linked_football_match_ids(session)
    have_pred = set(
        await session.scalars(select(MatchApiPrediction.match_id))
    )
    pending = [
        m
        for m in await upcoming_football_matches(session, for_odds_sync=True)
        if m.id in linked and m.id not in have_pred
    ]
    if limit is not None:
        return pending[:limit]
    return pending


async def sync_prematch_api_predictions(
    session: AsyncSession, *, limit: int | None = None
) -> int:
    """Backfill прогнозов API-Football для очереди odds (без отдельного окна 48ч)."""
    from src.config import settings

    batch = limit if limit is not None else settings.api_football_odds_batch_size
    matches = await matches_pending_api_predictions(session, limit=batch)
    n = 0
    for m in matches:
        if await fetch_api_prediction(session, m):
            n += 1
    await session.commit()
    return n
