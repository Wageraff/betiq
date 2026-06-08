"""Запись вызовов Claude API в ai_usage_log."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import AiUsageLog


async def record_ai_usage(
    session: AsyncSession,
    *,
    model: str,
    input_tokens: int,
    output_tokens: int,
    match_id: int | None = None,
    source: str = "summary",
) -> None:
    session.add(
        AiUsageLog(
            match_id=match_id,
            source=source,
            model=model,
            input_tokens=max(0, int(input_tokens or 0)),
            output_tokens=max(0, int(output_tokens or 0)),
        )
    )
