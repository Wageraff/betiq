"""Обновление полей матча из ответа API-Football (EN competition, round, venue)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api_clients.api_football import ApiFootballClient
from src.api_clients.constants import PROVIDER_API_FOOTBALL
from src.api_clients.external_ids import get_match_external_id
from src.db.models import CompetitionExternalId, Match, MatchExternalId


async def apply_fixture_fields(
    session: AsyncSession, match: Match, fixture: dict
) -> None:
    """Перезаписать competition/round/venue/score из API (английские названия)."""
    fix = fixture.get("fixture") or {}
    league = fixture.get("league") or {}
    goals = fixture.get("goals") or {}
    score = fixture.get("score") or {}
    ht = score.get("halftime") or {}

    league_name = (league.get("name") or "").strip()
    if league_name:
        match.competition = league_name

    league_id = league.get("id")
    if league_id is not None:
        cid = await session.scalar(
            select(CompetitionExternalId.competition_id).where(
                CompetitionExternalId.provider == PROVIDER_API_FOOTBALL,
                CompetitionExternalId.external_id == str(league_id),
            )
        )
        if cid:
            match.competition_id = cid

    status = (fix.get("status") or {}).get("short")
    if status:
        match.status = status

    venue = fix.get("venue") or {}
    if venue.get("name"):
        match.venue_name = venue.get("name")
    if venue.get("city"):
        match.venue_city = venue.get("city")

    if league.get("season"):
        match.season = str(league.get("season"))
    if league.get("round"):
        match.round = league.get("round")

    if goals.get("home") is not None:
        match.score_home = goals.get("home")
    if goals.get("away") is not None:
        match.score_away = goals.get("away")
    if ht.get("home") is not None:
        match.score_ht_home = ht.get("home")
    if ht.get("away") is not None:
        match.score_ht_away = ht.get("away")


async def refresh_linked_football_fields(
    session: AsyncSession, *, limit: int = 40
) -> int:
    """Обновить competition/round/venue у уже связанных предстоящих матчей."""
    from datetime import datetime, timedelta, timezone

    client = ApiFootballClient()
    if not client.enabled:
        return 0

    since = datetime.now(timezone.utc) - timedelta(days=3)
    linked = select(MatchExternalId.match_id).where(
        MatchExternalId.provider == PROVIDER_API_FOOTBALL
    )
    matches = (
        await session.scalars(
            select(Match)
            .where(
                Match.id.in_(linked),
                Match.sport == "football",
                Match.match_date.isnot(None),
                Match.match_date >= since,
            )
            .order_by(Match.match_date.asc())
            .limit(limit)
        )
    ).all()

    updated = 0
    for match in matches:
        fixture_id = await get_match_external_id(
            session, match.id, PROVIDER_API_FOOTBALL
        )
        if not fixture_id:
            continue
        try:
            rows = await client.get_fixtures(fixture=fixture_id)
            if rows:
                await apply_fixture_fields(session, match, rows[0])
                updated += 1
        except Exception:
            continue
    return updated
