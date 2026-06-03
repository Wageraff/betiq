"""Публичные эндпоинты матчей."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.deps import get_db
from src.api.schemas import (
    AiOut,
    BetOut,
    MatchBriefOut,
    MatchDetailOut,
    MatchDetailResponse,
    MatchesListResponse,
    PredictionOut,
    PredictionsOnlyResponse,
    SportCountOut,
    SportsListResponse,
)
from src.db.models import Match, Prediction

router = APIRouter(prefix="/api/v1", tags=["matches"])


def _ai_from_match(match: Match) -> Optional[AiOut]:
    if not match.ai_summary and not match.ai_top_pick:
        return None
    return AiOut(
        summary=match.ai_summary,
        top_pick=match.ai_top_pick,
        confidence=match.ai_confidence,
        generated_at=match.ai_generated_at,
    )


def _prediction_out(pred: Prediction) -> PredictionOut:
    source_name = pred.source.name if pred.source else "unknown"
    bets = [
        BetOut(
            bet_type=b.bet_type,
            bet_pick=b.bet_pick,
            odds=b.odds,
            is_main=b.is_main,
        )
        for b in sorted(pred.bets, key=lambda x: x.sort_order)
    ]
    return PredictionOut(
        id=pred.id,
        source=source_name,
        language=pred.language,
        author=pred.author,
        title=pred.title,
        source_url=pred.source_url,
        published_at=pred.published_at,
        bets=bets,
    )


@router.get("/matches", response_model=MatchesListResponse, response_model_by_alias=True)
async def list_matches(
    sport: Optional[str] = None,
    date_from: Optional[datetime] = Query(None, alias="date_from"),
    date_to: Optional[datetime] = Query(None, alias="date_to"),
    language: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
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
    if language:
        subq = (
            select(Prediction.match_id)
            .where(Prediction.language == language)
            .distinct()
            .scalar_subquery()
        )
        stmt = stmt.where(Match.id.in_(subq))
        count_stmt = count_stmt.where(Match.id.in_(subq))

    total = await db.scalar(count_stmt) or 0
    stmt = (
        stmt.order_by(Match.match_date.desc().nullslast(), Match.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    matches = (await db.scalars(stmt)).all()

    items = [
        MatchBriefOut(
            id=m.id,
            slug=m.slug,
            team_home=m.team_home,
            team_away=m.team_away,
            sport=m.sport,
            competition=m.competition,
            match_date=m.match_date,
            predictions_count=m.predictions_count or 0,
            ai=_ai_from_match(m),
        )
        for m in matches
    ]
    return MatchesListResponse(items=items, page=page, limit=limit, total=total)


@router.get("/sports", response_model=SportsListResponse, response_model_by_alias=True)
async def list_sports(db: AsyncSession = Depends(get_db)):
    rows = await db.execute(
        select(Match.sport, func.count(Match.id))
        .where(Match.sport.isnot(None))
        .group_by(Match.sport)
        .order_by(func.count(Match.id).desc())
    )
    sports = [SportCountOut(sport=row[0], count=row[1]) for row in rows.all()]
    return SportsListResponse(sports=sports)


async def _get_match_by_slug(db: AsyncSession, slug: str) -> Match:
    match = await db.scalar(
        select(Match)
        .where(Match.slug == slug)
        .options(
            selectinload(Match.predictions).selectinload(Prediction.bets),
            selectinload(Match.predictions).selectinload(Prediction.source),
        )
    )
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    return match


@router.get(
    "/matches/{slug}",
    response_model=MatchDetailResponse,
    response_model_by_alias=True,
)
async def get_match(slug: str, db: AsyncSession = Depends(get_db)):
    match = await _get_match_by_slug(db, slug)
    predictions = sorted(match.predictions, key=lambda p: p.scraped_at or datetime.min)
    return MatchDetailResponse(
        match=MatchDetailOut(
            id=match.id,
            slug=match.slug,
            team_home=match.team_home,
            team_away=match.team_away,
            sport=match.sport,
            competition=match.competition,
            match_date=match.match_date,
            predictions_count=match.predictions_count or 0,
            ai=_ai_from_match(match),
        ),
        predictions=[_prediction_out(p) for p in predictions],
    )


@router.get(
    "/matches/{slug}/predictions",
    response_model=PredictionsOnlyResponse,
    response_model_by_alias=True,
)
async def get_match_predictions(
    slug: str,
    language: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    match = await _get_match_by_slug(db, slug)
    preds = match.predictions
    if language:
        preds = [p for p in preds if p.language == language]
    preds = sorted(preds, key=lambda p: p.scraped_at or datetime.min)
    return PredictionsOnlyResponse(predictions=[_prediction_out(p) for p in preds])
