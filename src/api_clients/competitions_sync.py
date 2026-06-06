"""Синхронизация справочника лиг из API-Football."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api_clients.api_football import ApiFootballClient
from src.api_clients.constants import PROVIDER_API_FOOTBALL
from src.db.models import Competition, CompetitionExternalId

log = logging.getLogger("competitions_sync")


async def sync_leagues_from_api_football(
    session: AsyncSession, *, season: int | None = None
) -> int:
    client = ApiFootballClient()
    if not client.enabled:
        return 0
    if season is None:
        season = datetime.now(timezone.utc).year

    rows = await client.get_leagues(season=season)
    synced = 0
    for item in rows:
        league = item.get("league") or {}
        country = item.get("country") or {}
        name = (league.get("name") or "").strip()
        if not name:
            continue
        sport = "football"
        comp = await session.scalar(
            select(Competition).where(
                func.lower(Competition.name) == name.lower(),
                Competition.sport == sport,
            )
        )
        if not comp:
            comp = Competition(
                name=name,
                sport=sport,
                country=country.get("name"),
                country_code=country.get("code"),
                logo_url=league.get("logo"),
                flag_url=country.get("flag"),
            )
            session.add(comp)
            await session.flush()
        else:
            if league.get("logo"):
                comp.logo_url = league.get("logo")
            if country.get("flag"):
                comp.flag_url = country.get("flag")

        ext_id = str(league.get("id") or "")
        if ext_id:
            row = await session.get(
                CompetitionExternalId, (comp.id, PROVIDER_API_FOOTBALL)
            )
            if row:
                row.external_id = ext_id
                row.external_name = name
                row.season = str(season)
            else:
                session.add(
                    CompetitionExternalId(
                        competition_id=comp.id,
                        provider=PROVIDER_API_FOOTBALL,
                        external_id=ext_id,
                        external_name=name,
                        season=str(season),
                    )
                )
        synced += 1
    await session.commit()
    log.info("Synced %s leagues from API-Football", synced)
    return synced
