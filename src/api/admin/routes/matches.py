"""Admin: матчи и прогнозы."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.admin.deps import require_admin
from src.api.admin.schemas import (
    AdminBetOut,
    AdminMatchBrief,
    AdminMatchDetail,
    AdminMatchesList,
    AdminPredictionOut,
)
from src.api.deps import get_db
from src.db.models import Match, Prediction

router = APIRouter(prefix="/matches", tags=["admin-matches"])


def _brief(m: Match) -> AdminMatchBrief:
    return AdminMatchBrief(
        id=m.id,
        match_key=m.match_key,
        slug=m.slug,
        team_home=m.team_home,
        team_away=m.team_away,
        team_home_id=m.team_home_id,
        team_away_id=m.team_away_id,
        sport=m.sport,
        competition=m.competition,
        match_date=m.match_date,
        predictions_count=m.predictions_count or 0,
        has_ai=bool(m.ai_summary),
        ai_confidence=m.ai_confidence,
    )


@router.get("", response_model=AdminMatchesList)
async def list_matches(
    sport: Optional[str] = None,
    q: Optional[str] = Query(None, description="Поиск по названию команд"),
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    has_ai: Optional[bool] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin),
):
    stmt = select(Match)
    count_stmt = select(func.count()).select_from(Match)

    if sport:
        stmt = stmt.where(Match.sport == sport)
        count_stmt = count_stmt.where(Match.sport == sport)
    if date_from:
        stmt = stmt.where(Match.match_date >= date_from)
        count_stmt = count_stmt.where(Match.match_date >= date_from)
    if date_to:
        stmt = stmt.where(Match.match_date <= date_to)
        count_stmt = count_stmt.where(Match.match_date <= date_to)
    if has_ai is True:
        stmt = stmt.where(Match.ai_summary.isnot(None))
        count_stmt = count_stmt.where(Match.ai_summary.isnot(None))
    elif has_ai is False:
        stmt = stmt.where(Match.ai_summary.is_(None))
        count_stmt = count_stmt.where(Match.ai_summary.is_(None))
    if q:
        like = f"%{q.strip()}%"
        flt = or_(Match.team_home.ilike(like), Match.team_away.ilike(like))
        stmt = stmt.where(flt)
        count_stmt = count_stmt.where(flt)

    total = await db.scalar(count_stmt) or 0
    stmt = (
        stmt.order_by(Match.match_date.desc().nullslast(), Match.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    matches = (await db.scalars(stmt)).all()
    return AdminMatchesList(
        items=[_brief(m) for m in matches],
        page=page,
        limit=limit,
        total=total,
    )


@router.get("/{match_id}", response_model=AdminMatchDetail)
async def get_match(
    match_id: int,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin),
):
    match = await db.scalar(
        select(Match)
        .where(Match.id == match_id)
        .options(
            selectinload(Match.predictions).selectinload(Prediction.bets),
            selectinload(Match.predictions).selectinload(Prediction.source),
        )
    )
    if not match:
        raise HTTPException(404, "Match not found")

    preds = []
    for p in sorted(match.predictions, key=lambda x: x.scraped_at or datetime.min):
        preds.append(
            AdminPredictionOut(
                id=p.id,
                source=p.source.name if p.source else "?",
                language=p.language,
                author=p.author,
                source_url=p.source_url,
                title=p.title,
                full_text=p.full_text,
                scraped_at=p.scraped_at,
                bets=[
                    AdminBetOut(
                        bet_pick=b.bet_pick,
                        odds=b.odds,
                        bet_type=b.bet_type,
                        is_main=b.is_main,
                    )
                    for b in sorted(p.bets, key=lambda x: x.sort_order)
                ],
            )
        )

    return AdminMatchDetail(
        match=_brief(match),
        predictions=preds,
        ai_summary=match.ai_summary,
        ai_top_pick=match.ai_top_pick,
        ai_confidence=match.ai_confidence,
        ai_generated_at=match.ai_generated_at,
        ai_model=match.ai_model,
    )
