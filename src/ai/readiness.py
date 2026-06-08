"""Условия готовности матча к однократной генерации AI-сводки."""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api_clients.constants import PROVIDER_API_FOOTBALL, PROVIDER_THE_ODDS_API
from src.api_clients.odds import odds_provider_for_market
from src.api_clients.odds_keys import odds_sport_keys_for_match
from src.config import settings
from src.db.models import Match, MatchApiPrediction, MatchExternalId, MatchOdds


@dataclass
class MatchAiContext:
    providers: set[str] = field(default_factory=set)
    has_api_prediction: bool = False
    the_odds_api_odds: int = 0


async def load_match_ai_contexts(
    session: AsyncSession, match_ids: list[int]
) -> dict[int, MatchAiContext]:
    if not match_ids:
        return {}

    ext_rows = (
        await session.execute(
            select(MatchExternalId.match_id, MatchExternalId.provider).where(
                MatchExternalId.match_id.in_(match_ids)
            )
        )
    ).all()
    ctx_map: dict[int, MatchAiContext] = {mid: MatchAiContext() for mid in match_ids}
    for mid, provider in ext_rows:
        ctx_map[mid].providers.add(provider)

    pred_ids = set(
        await session.scalars(
            select(MatchApiPrediction.match_id).where(
                MatchApiPrediction.match_id.in_(match_ids)
            )
        )
    )
    for mid in pred_ids:
        ctx_map[mid].has_api_prediction = True

    odds_rows = (
        await session.execute(
            select(MatchOdds.match_id, MatchOdds.market).where(
                MatchOdds.match_id.in_(match_ids)
            )
        )
    ).all()
    for mid, market in odds_rows:
        if odds_provider_for_market(market) == PROVIDER_THE_ODDS_API:
            ctx_map[mid].the_odds_api_odds += 1

    return ctx_map


def missing_ai_requirements(
    match: Match,
    ctx: MatchAiContext,
    *,
    api_sync_enabled: bool | None = None,
    the_odds_mappable: bool | None = None,
) -> list[str]:
    """Что ещё не готово. Пустой список — можно генерировать."""
    if match.ai_generated_at is not None:
        return ["already_generated"]

    missing: list[str] = []
    if (match.predictions_count or 0) < 2:
        missing.append("expert_predictions")

    if api_sync_enabled is None:
        api_sync_enabled = settings.api_sync_enabled
    if not api_sync_enabled:
        return missing

    sport = (match.sport or "").strip().lower()
    if sport == "football":
        if PROVIDER_API_FOOTBALL not in ctx.providers:
            missing.append("api_football")
        if not ctx.has_api_prediction:
            missing.append("api_football_prediction")
        if ctx.the_odds_api_odds <= 0:
            missing.append("the_odds_api")
        return missing

    if the_odds_mappable is False:
        return missing

    if the_odds_mappable is True and ctx.the_odds_api_odds <= 0:
        missing.append("the_odds_api")

    return missing


def is_match_ai_ready(
    match: Match,
    ctx: MatchAiContext,
    *,
    api_sync_enabled: bool | None = None,
    the_odds_mappable: bool | None = None,
) -> bool:
    return not missing_ai_requirements(
        match,
        ctx,
        api_sync_enabled=api_sync_enabled,
        the_odds_mappable=the_odds_mappable,
    )


async def is_match_ai_ready_async(
    session: AsyncSession, match: Match, ctx: MatchAiContext | None = None
) -> bool:
    if ctx is None:
        loaded = await load_match_ai_contexts(session, [match.id])
        ctx = loaded.get(match.id, MatchAiContext())

    the_odds_mappable: bool | None = None
    if settings.api_sync_enabled and (match.sport or "").strip().lower() != "football":
        keys = await odds_sport_keys_for_match(session, match)
        the_odds_mappable = bool(keys)

    return is_match_ai_ready(
        match, ctx, the_odds_mappable=the_odds_mappable
    )


async def matches_ready_for_ai(session: AsyncSession) -> list[int]:
    """Матчи с 2+ прогнозами, без сводки, со всеми собранными внешними данными."""
    candidates = list(
        (
            await session.scalars(
                select(Match).where(
                    Match.predictions_count >= 2,
                    Match.ai_generated_at.is_(None),
                )
            )
        ).all()
    )
    if not candidates:
        return []

    ids = [m.id for m in candidates]
    contexts = await load_match_ai_contexts(session, ids)
    ready: list[int] = []

    for match in candidates:
        ctx = contexts.get(match.id, MatchAiContext())
        the_odds_mappable: bool | None = None
        if settings.api_sync_enabled and (match.sport or "").strip().lower() != "football":
            keys = await odds_sport_keys_for_match(session, match)
            the_odds_mappable = bool(keys)

        if is_match_ai_ready(
            match, ctx, the_odds_mappable=the_odds_mappable
        ):
            ready.append(match.id)

    return ready


async def count_matches_awaiting_data(session: AsyncSession) -> int:
    """Матчи с 2+ прогнозами без сводки, но ещё без полного набора API-данных."""
    candidates = list(
        (
            await session.scalars(
                select(Match.id).where(
                    Match.predictions_count >= 2,
                    Match.ai_generated_at.is_(None),
                )
            )
        ).all()
    )
    ready = set(await matches_ready_for_ai(session))
    return len([mid for mid in candidates if mid not in ready])
