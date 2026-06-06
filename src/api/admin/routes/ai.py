"""Admin: AI-сводки."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.prompt_template import load_prompt_template, resolve_prompt_path
from src.api.admin.deps import require_admin
from src.api.admin.schemas import AdminAiMatchBrief, AdminAiUpdate
from src.api.deps import get_db
from src.db.models import Match

router = APIRouter(prefix="/ai", tags=["admin-ai"])


@router.get("/matches", response_model=list[AdminAiMatchBrief])
async def list_ai_matches(
    has_ai: Optional[bool] = None,
    min_predictions: int = Query(2, ge=1),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin),
):
    stmt = select(Match).where(Match.predictions_count >= min_predictions)
    if has_ai is True:
        stmt = stmt.where(Match.ai_summary.isnot(None))
    elif has_ai is False:
        stmt = stmt.where(Match.ai_summary.is_(None))
    stmt = stmt.order_by(Match.match_date.desc().nullslast()).limit(100)
    rows = (await db.scalars(stmt)).all()
    return [_ai_brief(m) for m in rows]


def _ai_brief(m: Match) -> AdminAiMatchBrief:
    return AdminAiMatchBrief(
        id=m.id,
        match_title=f"{m.team_home} vs {m.team_away}",
        sport=m.sport,
        match_date=m.match_date,
        predictions_count=m.predictions_count or 0,
        has_ai=bool(m.ai_summary),
        ai_summary=m.ai_summary,
        ai_top_pick=m.ai_top_pick,
        ai_confidence=m.ai_confidence,
        ai_generated_at=m.ai_generated_at,
    )


@router.patch("/matches/{match_id}", response_model=AdminAiMatchBrief)
async def update_ai_match(
    match_id: int,
    body: AdminAiUpdate,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin),
):
    match = await db.get(Match, match_id)
    if not match:
        raise HTTPException(404, "Match not found")
    if body.ai_summary is not None:
        text = body.ai_summary.strip()
        match.ai_summary = text or None
    if body.ai_top_pick is not None:
        pick = body.ai_top_pick.strip()
        match.ai_top_pick = pick or None
    await db.commit()
    await db.refresh(match)
    return _ai_brief(match)


@router.get("/prompt-template")
async def get_prompt_template(_: None = Depends(require_admin)):
    path = resolve_prompt_path()
    try:
        text = load_prompt_template()
    except FileNotFoundError:
        text = ""
    return {"path": str(path), "content": text}
