"""Загрузка данных внешних API для админки."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import (
    Match,
    MatchExternalId,
    MatchLineup,
    MatchOdds,
    MatchStats,
    OddsHistory,
    TeamForm,
)


async def load_list_meta(
    session: AsyncSession, match_ids: list[int]
) -> dict[int, dict[str, object]]:
    if not match_ids:
        return {}

    ext_rows = (
        await session.execute(
            select(MatchExternalId.match_id, MatchExternalId.provider).where(
                MatchExternalId.match_id.in_(match_ids)
            )
        )
    ).all()
    ext_map: dict[int, set[str]] = {}
    for mid, provider in ext_rows:
        ext_map.setdefault(mid, set()).add(provider)

    odds_counts = dict(
        (
            await session.execute(
                select(MatchOdds.match_id, func.count())
                .where(MatchOdds.match_id.in_(match_ids))
                .group_by(MatchOdds.match_id)
            )
        ).all()
    )
    stats_counts = dict(
        (
            await session.execute(
                select(MatchStats.match_id, func.count())
                .where(MatchStats.match_id.in_(match_ids))
                .group_by(MatchStats.match_id)
            )
        ).all()
    )

    out: dict[int, dict[str, object]] = {}
    for mid in match_ids:
        providers = ext_map.get(mid, set())
        out[mid] = {
            "has_api_football": "api_football" in providers,
            "has_odds_api": "the_odds_api" in providers,
            "odds_count": int(odds_counts.get(mid, 0)),
            "has_match_stats": int(stats_counts.get(mid, 0)) > 0,
        }
    return out


async def load_match_api_bundle(session: AsyncSession, match: Match) -> dict:
    external_ids = [
        {
            "provider": e.provider,
            "external_id": e.external_id,
            "link_method": e.link_method,
            "confidence": e.confidence,
            "linked_at": e.linked_at,
        }
        for e in match.external_ids
    ]

    stats = [
        {
            "side": s.side,
            "half": s.half,
            "shots_on_goal": s.shots_on_goal,
            "shots_total": s.shots_total,
            "corners": s.corners,
            "fouls": s.fouls,
            "yellow_cards": s.yellow_cards,
            "red_cards": s.red_cards,
            "possession": s.possession,
            "fetched_at": s.fetched_at,
        }
        for s in sorted(match.stats, key=lambda x: x.side)
    ]

    odds = (
        await session.scalars(
            select(MatchOdds)
            .where(MatchOdds.match_id == match.id)
            .order_by(MatchOdds.market, MatchOdds.bookmaker, MatchOdds.outcome)
            .limit(200)
        )
    ).all()
    odds_rows = [
        {
            "bookmaker": o.bookmaker,
            "market": o.market,
            "outcome": o.outcome,
            "odds": o.odds,
            "point": o.point,
            "is_live": o.is_live,
            "recorded_at": o.recorded_at,
        }
        for o in odds
    ]

    history = (
        await session.scalars(
            select(OddsHistory)
            .where(OddsHistory.match_id == match.id)
            .order_by(OddsHistory.recorded_at.desc())
            .limit(30)
        )
    ).all()
    history_rows = [
        {
            "bookmaker": h.bookmaker,
            "market": h.market,
            "outcome": h.outcome,
            "odds_prev": h.odds_prev,
            "odds_curr": h.odds_curr,
            "movement_pct": h.movement_pct,
            "direction": h.direction,
            "is_significant": h.is_significant,
            "recorded_at": h.recorded_at,
        }
        for h in history
    ]

    lineups = [
        {
            "side": ln.side,
            "formation": ln.formation,
            "coach_name": ln.coach_name,
            "players_count": len(ln.lineup_json or []),
            "fetched_at": ln.fetched_at,
        }
        for ln in match.lineups
    ]

    form_home: list[dict] = []
    form_away: list[dict] = []
    if match.team_home_id:
        form_home = await _team_form_rows(session, match.team_home_id)
    if match.team_away_id:
        form_away = await _team_form_rows(session, match.team_away_id)

    score = None
    if match.score_home is not None and match.score_away is not None:
        score = f"{match.score_home}-{match.score_away}"

    return {
        "status": match.status,
        "venue_name": match.venue_name,
        "venue_city": match.venue_city,
        "season": match.season,
        "round": match.round,
        "score": score,
        "score_ht": (
            f"{match.score_ht_home}-{match.score_ht_away}"
            if match.score_ht_home is not None and match.score_ht_away is not None
            else None
        ),
        "stats_fetched_at": match.stats_fetched_at,
        "odds_fetched_at": match.odds_fetched_at,
        "external_ids": external_ids,
        "match_stats": stats,
        "odds": odds_rows,
        "odds_history": history_rows,
        "lineups": lineups,
        "team_form_home": form_home,
        "team_form_away": form_away,
    }


async def _team_form_rows(session: AsyncSession, team_id: int) -> list[dict]:
    rows = (
        await session.scalars(
            select(TeamForm)
            .where(TeamForm.team_id == team_id)
            .order_by(TeamForm.match_date.desc())
            .limit(10)
        )
    ).all()
    return [
        {
            "match_date": r.match_date,
            "opponent_name": r.opponent_name,
            "is_home": r.is_home,
            "result": r.result,
            "goals_scored": r.goals_scored,
            "goals_conceded": r.goals_conceded,
            "competition_name": r.competition_name,
        }
        for r in rows
    ]
