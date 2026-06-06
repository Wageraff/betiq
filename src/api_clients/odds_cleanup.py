"""Полная очистка коэффициентов в БД перед пересборкой."""
from __future__ import annotations

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Match, MatchOdds, OddsHistory, OddsSyncLog


async def clear_all_odds_data(session: AsyncSession) -> dict[str, int]:
    """Удалить все match_odds, odds_history, сбросить odds_fetched_at и троттлинг."""
    odds_before = int(
        await session.scalar(select(func.count()).select_from(MatchOdds)) or 0
    )
    hist_before = int(
        await session.scalar(select(func.count()).select_from(OddsHistory)) or 0
    )
    log_before = int(
        await session.scalar(select(func.count()).select_from(OddsSyncLog)) or 0
    )

    await session.execute(delete(MatchOdds))
    await session.execute(delete(OddsHistory))
    await session.execute(delete(OddsSyncLog))
    match_res = await session.execute(update(Match).values(odds_fetched_at=None))
    await session.commit()

    return {
        "match_odds_deleted": odds_before,
        "odds_history_deleted": hist_before,
        "odds_sync_log_deleted": log_before,
        "matches_odds_reset": match_res.rowcount or 0,
    }
