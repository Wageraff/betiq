"""Admin: запуск парсера / health / AI."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.api.admin.deps import require_admin
from src.api.admin.schemas import ActionLogOut, ActionRequest, ActionResponse
from src.api.admin.services import actions as job_actions

router = APIRouter(prefix="/actions", tags=["admin-actions"])


@router.post("/scrape", response_model=ActionResponse)
async def action_scrape(body: ActionRequest, _: None = Depends(require_admin)):
    if not body.source:
        raise HTTPException(400, "source is required")
    job_id = await job_actions.scrape_source(
        body.source, body.limit or 10, body.force
    )
    return ActionResponse(ok=True, message="Scrape started", job_id=job_id)


@router.post("/health-check", response_model=ActionResponse)
async def action_health(body: ActionRequest, _: None = Depends(require_admin)):
    job_id = await job_actions.health_check(body.source)
    return ActionResponse(ok=True, message="Health check started", job_id=job_id)


@router.post("/diagnose", response_model=ActionResponse)
async def action_diagnose(body: ActionRequest, _: None = Depends(require_admin)):
    if not body.source:
        raise HTTPException(400, "source is required")
    job_id = await job_actions.diagnose(body.source)
    return ActionResponse(ok=True, message="Diagnose started", job_id=job_id)


@router.post("/ai-summary", response_model=ActionResponse)
async def action_ai(body: ActionRequest, _: None = Depends(require_admin)):
    if not body.match_id:
        raise HTTPException(400, "match_id is required")
    job_id = await job_actions.ai_summary(body.match_id, body.force)
    return ActionResponse(ok=True, message="AI summary started", job_id=job_id)


@router.get("/jobs/{job_id}/log", response_model=ActionLogOut)
async def job_log(job_id: str, _: None = Depends(require_admin)):
    state = job_actions.get_job_log(job_id)
    if not state:
        raise HTTPException(404, "Job not found")
    return ActionLogOut(lines=list(state.lines))
