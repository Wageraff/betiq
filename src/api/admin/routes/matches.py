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
    AdminMatchApiData,
    AdminMatchBrief,
    AdminMatchDetail,
    AdminMatchOddsList,
    AdminMatchesList,
    AdminPredictionOut,
)
from src.api.admin.services.match_api_data import (
    load_list_meta,
    load_match_api_bundle,
    load_match_odds_rows,
    load_odds_market_summary,
)
from src.api.deps import get_db
from src.db.models import Match, MatchExternalId, Prediction

router = APIRouter(prefix="/matches", tags=["admin-matches"])


def _score_str(m: Match) -> Optional[str]:
    if m.score_home is not None and m.score_away is not None:
        return f"{m.score_home}-{m.score_away}"
    return None


def _brief(m: Match, meta: dict | None = None) -> AdminMatchBrief:
    meta = meta or {}
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
        round=m.round,
        venue_name=m.venue_name,
        venue_city=m.venue_city,
        match_date=m.match_date,
        status=m.status,
        score=_score_str(m),
        predictions_count=m.predictions_count or 0,
        has_ai=bool(m.ai_summary),
        ai_confidence=m.ai_confidence,
        has_api_football=bool(meta.get("has_api_football")),
        has_odds_api=bool(meta.get("has_odds_api")),
        odds_count=int(meta.get("odds_count", 0)),
        has_match_stats=bool(meta.get("has_match_stats")),
    )


@router.get("", response_model=AdminMatchesList)
async def list_matches(
    sport: Optional[str] = None,
    q: Optional[str] = Query(None, description="Поиск по названию команд"),
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    has_ai: Optional[bool] = None,
    has_api: Optional[bool] = Query(None, description="Есть линковка API-Football или Odds"),
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
    if has_api is True:
        linked = select(MatchExternalId.match_id)
        stmt = stmt.where(Match.id.in_(linked))
        count_stmt = count_stmt.where(Match.id.in_(linked))
    elif has_api is False:
        linked = select(MatchExternalId.match_id)
        stmt = stmt.where(Match.id.not_in(linked))
        count_stmt = count_stmt.where(Match.id.not_in(linked))

    total = await db.scalar(count_stmt) or 0
    stmt = (
        stmt.order_by(Match.match_date.desc().nullslast(), Match.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    matches = (await db.scalars(stmt)).all()
    meta_map = await load_list_meta(db, [m.id for m in matches])

    items = [_brief(m, meta_map.get(m.id)) for m in matches]

    return AdminMatchesList(
        items=items,
        page=page,
        limit=limit,
        total=total,
    )


@router.get("/{match_id}/odds", response_model=AdminMatchOddsList)
async def get_match_odds(
    match_id: int,
    market: Optional[str] = Query(None, description="Фильтр по рынку (h2h, Match Winner, …)"),
    limit: int = Query(500, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin),
):
    exists = await db.scalar(select(Match.id).where(Match.id == match_id))
    if not exists:
        raise HTTPException(404, "Match not found")

    total, markets = await load_odds_market_summary(db, match_id)
    market_count = 0
    if market:
        for m in markets:
            if m["market"] == market:
                market_count = int(m["count"])
                break

    items = await load_match_odds_rows(
        db, match_id, market=market, limit=limit, offset=offset
    )
    return AdminMatchOddsList(
        match_id=match_id,
        market=market,
        total=total,
        market_count=market_count or total,
        items=items,
    )


@router.get("/{match_id}", response_model=AdminMatchDetail)
async def get_match(
    match_id: int,
    odds_market: Optional[str] = Query(None, description="Рынок odds для первой загрузки"),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin),
):
    match = await db.scalar(
        select(Match)
        .where(Match.id == match_id)
        .options(
            selectinload(Match.predictions).selectinload(Prediction.bets),
            selectinload(Match.predictions).selectinload(Prediction.source),
            selectinload(Match.external_ids),
            selectinload(Match.stats),
            selectinload(Match.lineups),
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

    meta_map = await load_list_meta(db, [match.id])
    bundle = await load_match_api_bundle(db, match, odds_market=odds_market)

    return AdminMatchDetail(
        match=_brief(match, meta_map.get(match.id)),
        predictions=preds,
        ai_summary=match.ai_summary,
        ai_top_pick=match.ai_top_pick,
        ai_confidence=match.ai_confidence,
        ai_generated_at=match.ai_generated_at,
        ai_model=match.ai_model,
        api_data=AdminMatchApiData.model_validate(bundle),
    )
