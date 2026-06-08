"""Сводка: какие матчи и лиги сейчас в очереди API-синка."""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api_clients.constants import PROVIDER_API_FOOTBALL, PROVIDER_THE_ODDS_API
from src.api_clients.football_odds_sync import upcoming_af_odds_match_ids
from src.api_clients.odds_keys import ODDS_KEY_LABELS, odds_sport_keys_for_match
from src.api_clients.odds_scope import (
    collect_odds_sport_keys,
    match_external_providers,
    match_odds_counts,
    upcoming_matches,
    upcoming_match_window,
)
from src.config import settings
from src.api_clients.stats_sync import matches_pending_api_predictions
from src.db.models import Match, MatchApiPrediction


def _markets_count(csv: str) -> int:
    return len([p for p in csv.split(",") if p.strip()])


async def fetch_sync_coverage(session: AsyncSession) -> dict:
    since, until = upcoming_match_window()
    matches = await upcoming_matches(session)
    match_ids = [m.id for m in matches]
    providers = await match_external_providers(session, match_ids)
    odds_counts = await match_odds_counts(session, match_ids)
    pred_ids = set(
        await session.scalars(
            select(MatchApiPrediction.match_id).where(
                MatchApiPrediction.match_id.in_(match_ids)
            )
        )
    ) if match_ids else set()
    by_key = await collect_odds_sport_keys(session, matches)

    bulk_markets = _markets_count(settings.the_odds_api_markets)
    event_markets = _markets_count(settings.the_odds_api_event_markets)

    sport_keys_out = []
    for key in sorted(by_key.keys()):
        group = by_key[key]
        sport_keys_out.append(
            {
                "sport_key": key,
                "label": ODDS_KEY_LABELS.get(key, key),
                "sport": group[0].sport if group else None,
                "match_count": len(group),
                "matches": [
                    _match_brief(
                        m,
                        providers=providers.get(m.id, set()),
                        odds_count=odds_counts.get(m.id, 0),
                        sport_keys=[key],
                    )
                    for m in group[:15]
                ],
            }
        )

    by_sport: dict[str, int] = defaultdict(int)
    for m in matches:
        by_sport[m.sport or "unknown"] += 1

    unmapped = []
    for m in matches:
        keys = await odds_sport_keys_for_match(session, m)
        if not keys:
            unmapped.append(
                _match_brief(
                    m,
                    providers=providers.get(m.id, set()),
                    odds_count=odds_counts.get(m.id, 0),
                    sport_keys=[],
                )
            )

    football_matches = [m for m in matches if m.sport == "football"]
    linked_odds = [
        m
        for m in football_matches
        if PROVIDER_THE_ODDS_API in providers.get(m.id, set())
    ][: settings.the_odds_api_event_batch_size]

    pred_pending = await matches_pending_api_predictions(
        session, limit=settings.api_football_odds_batch_size
    )
    pred_have = int(
        await session.scalar(select(func.count()).select_from(MatchApiPrediction)) or 0
    )

    af_queue_ids = await upcoming_af_odds_match_ids(session)
    af_matches = []
    if af_queue_ids:
        af_rows = (
            await session.scalars(select(Match).where(Match.id.in_(af_queue_ids)))
        ).all()
        af_by_id = {m.id: m for m in af_rows}
        for mid in af_queue_ids[: settings.api_football_odds_batch_size]:
            m = af_by_id.get(mid)
            if m:
                af_matches.append(
                    _match_brief(
                        m,
                        providers=providers.get(m.id, set()),
                        odds_count=odds_counts.get(m.id, 0),
                        sport_keys=await odds_sport_keys_for_match(session, m),
                        has_api_prediction=m.id in pred_ids,
                    )
                )

    from src.api.admin.services.api_sync_admin import fetch_db_counts

    counts = await fetch_db_counts(session)

    return {
        "odds_sync_mode": settings.odds_sync_mode,
        "window": {
            "since": since,
            "until": until,
            "days_ahead": settings.odds_upcoming_days_ahead,
            "skip_finished_hours": settings.odds_skip_finished_hours,
        },
        "upcoming_total": len(matches),
        "upcoming_by_sport": dict(sorted(by_sport.items())),
        "the_odds_api": {
            "bulk_sport_keys": sport_keys_out,
            "bulk_sport_key_count": len(by_key),
            "bulk_credits_per_run": len(by_key) * bulk_markets,
            "bulk_markets": settings.the_odds_api_markets,
            "event_markets": settings.the_odds_api_event_markets,
            "event_match_count": len(linked_odds),
            "event_credits_per_run": min(
                len(linked_odds), settings.the_odds_api_event_batch_size
            )
            * event_markets,
            "unmapped_match_count": len(unmapped),
            "unmapped_matches": unmapped[:25],
        },
        "api_football_odds": {
            "enabled": settings.api_football_odds_enabled,
            "batch_size": settings.api_football_odds_batch_size,
            "days_ahead": settings.api_football_odds_days_ahead,
            "queue_count": len(af_queue_ids),
            "matches": af_matches,
        },
        "api_football_predictions": {
            "with_odds_sync": True,
            "stored_count": pred_have,
            "pending_count": len(pred_pending),
            "batch_size": settings.api_football_odds_batch_size,
            "matches": [
                _match_brief(
                    m,
                    providers=providers.get(m.id, set()),
                    odds_count=odds_counts.get(m.id, 0),
                    sport_keys=[],
                    has_api_prediction=False,
                )
                for m in pred_pending[:15]
            ],
        },
        "odds_in_db": {
            "api_football": counts.get("match_odds_api_football", 0),
            "the_odds_api": counts.get("match_odds_the_odds_api", 0),
        },
    }


def _match_brief(
    m: Match,
    *,
    providers: set[str],
    odds_count: int,
    sport_keys: list[str],
    has_api_prediction: bool | None = None,
) -> dict:
    return {
        "id": m.id,
        "sport": m.sport,
        "team_home": m.team_home,
        "team_away": m.team_away,
        "competition": m.competition,
        "match_date": m.match_date,
        "status": m.status,
        "has_api_football": PROVIDER_API_FOOTBALL in providers,
        "has_the_odds_api": PROVIDER_THE_ODDS_API in providers,
        "odds_count": odds_count,
        "odds_fetched_at": m.odds_fetched_at,
        "has_api_prediction": has_api_prediction,
        "sport_keys": sport_keys,
    }
