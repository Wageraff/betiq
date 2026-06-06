"""Admin: управление лигами и синхронизацией."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.admin.deps import require_admin
from src.api.admin.schemas import (
    ApiQuotaStatusOut,
    CompetitionSyncNowOut,
    CompetitionTrackingOut,
    CompetitionTrackingUpdate,
    CompetitionsListOut,
)
from src.api.admin.services.competitions_admin import (
    api_quota_status,
    list_competitions,
    sync_competition_now,
    update_competition,
)
from src.api.deps import get_db

router = APIRouter(prefix="/competitions", tags=["admin-competitions"])


@router.get("", response_model=CompetitionsListOut)
async def get_competitions(
    sport: Optional[str] = None,
    is_tracked: Optional[bool] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin),
):
    items, total = await list_competitions(
        db, sport=sport, is_tracked=is_tracked, page=page, limit=limit
    )
    quota = await api_quota_status(db)
    return CompetitionsListOut(
        items=[CompetitionTrackingOut(**row) for row in items],
        total=total,
        page=page,
        limit=limit,
        quota=ApiQuotaStatusOut(**quota),
    )


@router.get("/api-status", response_model=ApiQuotaStatusOut)
async def get_api_quota_status(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin),
):
    return ApiQuotaStatusOut(**(await api_quota_status(db)))


@router.patch("/{competition_id}", response_model=CompetitionTrackingOut)
async def patch_competition(
    competition_id: int,
    body: CompetitionTrackingUpdate,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin),
):
    comp = await update_competition(
        db,
        competition_id,
        is_tracked=body.is_tracked,
        sync_odds=body.sync_odds,
        sync_stats=body.sync_stats,
        sync_lineups=body.sync_lineups,
        odds_markets=body.odds_markets,
        odds_days_ahead=body.odds_days_ahead,
        unset_odds_days_ahead=body.clear_odds_days_ahead,
    )
    if not comp:
        raise HTTPException(404, "Competition not found")
    items, _ = await list_competitions(
        db, sport=comp.sport, page=1, limit=200
    )
    row = next((i for i in items if i["id"] == competition_id), None)
    if row:
        return CompetitionTrackingOut(**row)
    from src.api.admin.services.competitions_admin import _parse_odds_markets

    return CompetitionTrackingOut(
        id=comp.id,
        name=comp.name,
        sport=comp.sport,
        country=comp.country,
        country_code=comp.country_code,
        matches_upcoming=0,
        is_tracked=comp.is_tracked,
        sync_odds=comp.sync_odds,
        sync_stats=comp.sync_stats,
        sync_lineups=comp.sync_lineups,
        odds_markets=_parse_odds_markets(comp.odds_markets),
        odds_days_ahead=comp.odds_days_ahead,
    )


@router.post("/{competition_id}/sync-now", response_model=CompetitionSyncNowOut)
async def post_competition_sync_now(
    competition_id: int,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin),
):
    result = await sync_competition_now(db, competition_id)
    if result.get("error") == "not_found":
        raise HTTPException(404, "Competition not found")
    return CompetitionSyncNowOut(**result)
