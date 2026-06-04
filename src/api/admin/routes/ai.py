"""Admin: AI-сводки."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.prompt_template import load_prompt_template, resolve_prompt_path
from src.api.admin.deps import require_admin
from src.api.admin.schemas import AdminAiMatchBrief
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
    return [
        AdminAiMatchBrief(
            id=m.id,
            match_title=f"{m.team_home} vs {m.team_away}",
            sport=m.sport,
            match_date=m.match_date,
            predictions_count=m.predictions_count or 0,
            has_ai=bool(m.ai_summary),
            ai_confidence=m.ai_confidence,
            ai_generated_at=m.ai_generated_at,
        )
        for m in rows
    ]


@router.get("/prompt-template")
async def get_prompt_template(_: None = Depends(require_admin)):
    path = resolve_prompt_path()
    try:
        text = load_prompt_template()
    except FileNotFoundError:
        text = ""
    return {"path": str(path), "content": text}
