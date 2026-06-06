"""Admin: Sport API sync (API-Football + The Odds API)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.api.admin.deps import require_admin
from src.api.admin.schemas import (
    ActionLogOut,
    ActionResponse,
    ApiProviderQuotaOut,
    ApiSyncActionRequest,
    ApiSyncCoverageOut,
    ApiSyncStatusOut,
)
from src.api.admin.services import actions as job_actions
from src.api.admin.services.api_sync_admin import fetch_db_counts, fetch_live_quotas
from src.api.admin.services.api_sync_coverage import fetch_sync_coverage
from src.api.deps import get_db
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api-sync", tags=["admin-api-sync"])


@router.get("/status", response_model=ApiSyncStatusOut)
async def api_sync_status(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin),
):
    live = await fetch_live_quotas()
    counts = await fetch_db_counts(db)
    coverage_raw = await fetch_sync_coverage(db)
    return ApiSyncStatusOut(
        api_sync_enabled=live["api_sync_enabled"],
        api_football=ApiProviderQuotaOut(**live["api_football"]),
        the_odds_api=ApiProviderQuotaOut(**live["the_odds_api"]),
        db_counts=counts,
        coverage=ApiSyncCoverageOut(**coverage_raw),
    )


@router.post("/run", response_model=ActionResponse)
async def api_sync_run(
    body: ApiSyncActionRequest,
    _: None = Depends(require_admin),
):
    try:
        job_id = await job_actions.api_sync(body.action)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return ActionResponse(ok=True, message=f"API sync: {body.action}", job_id=job_id)


@router.get("/jobs/{job_id}/log", response_model=ActionLogOut)
async def api_sync_job_log(job_id: str, _: None = Depends(require_admin)):
    state = job_actions.get_job_log(job_id)
    if not state:
        raise HTTPException(404, "Job not found")
    return ActionLogOut(lines=list(state.lines))
