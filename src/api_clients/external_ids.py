"""CRUD для внешних ID."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import MatchExternalId, Team, TeamExternalId


async def get_team_external_id(
    session: AsyncSession, team_id: int | None, provider: str
) -> str | None:
    if not team_id:
        return None
    row = await session.get(TeamExternalId, (team_id, provider))
    return row.external_id if row else None


async def save_team_external_id(
    session: AsyncSession,
    team_id: int,
    provider: str,
    external_id: str,
    *,
    external_name: str | None = None,
    verified: bool = False,
) -> None:
    row = await session.get(TeamExternalId, (team_id, provider))
    if row:
        row.external_id = external_id
        if external_name:
            row.external_name = external_name
    else:
        session.add(
            TeamExternalId(
                team_id=team_id,
                provider=provider,
                external_id=external_id,
                external_name=external_name,
                verified=verified,
            )
        )


async def save_match_external_id(
    session: AsyncSession,
    match_id: int,
    provider: str,
    external_id: str,
    *,
    link_method: str = "auto",
    confidence: float | None = None,
) -> None:
    row = await session.get(MatchExternalId, (match_id, provider))
    if row:
        row.external_id = external_id
        row.link_method = link_method
        row.confidence = confidence
        row.linked_at = datetime.now(timezone.utc)
    else:
        session.add(
            MatchExternalId(
                match_id=match_id,
                provider=provider,
                external_id=external_id,
                link_method=link_method,
                confidence=confidence,
            )
        )


async def get_match_external_id(
    session: AsyncSession, match_id: int, provider: str
) -> str | None:
    row = await session.get(MatchExternalId, (match_id, provider))
    return row.external_id if row else None


async def delete_match_external_id(
    session: AsyncSession, match_id: int, provider: str
) -> bool:
    row = await session.get(MatchExternalId, (match_id, provider))
    if not row:
        return False
    await session.delete(row)
    return True


async def sync_team_logo_from_api(
    session: AsyncSession, team: Team, logo_url: str | None
) -> bool:
    """logo_path (ручная загрузка) имеет приоритет над logo_url из API."""
    if not logo_url or team.logo_path or team.logo_url:
        return False
    team.logo_url = logo_url
    team.logo_fetched_at = datetime.now(timezone.utc)
    return True


async def matches_without_provider(
    session: AsyncSession,
    provider: str,
    *,
    limit: int = 50,
    sport: str | None = None,
):
    from sqlalchemy import case

    from src.db.models import Match

    now = datetime.now(timezone.utc)
    since = now - timedelta(days=30)
    linked = select(MatchExternalId.match_id).where(
        MatchExternalId.provider == provider
    )
    # Сначала предстоящие (ближайшие), потом прошедшие — иначе ЧМ/lineups не доходят.
    upcoming_first = case((Match.match_date >= now, 0), else_=1)
    q = (
        select(Match)
        .where(Match.id.not_in(linked))
        .where(Match.match_date.isnot(None))
        .where(Match.match_date >= since)
        .order_by(upcoming_first, Match.match_date.asc())
        .limit(limit)
    )
    if sport:
        q = q.where(Match.sport == sport)
    return list((await session.scalars(q)).all())
