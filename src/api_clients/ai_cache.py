"""Кэш ответов AI-чатбота."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import AiChatCache, Match


def build_cache_key(match_id: int, question_type: str, language: str) -> str:
    return f"{match_id}:{question_type}:{language}"


async def get_cached_response(
    session: AsyncSession, match_id: int, question_type: str, language: str
) -> AiChatCache | None:
    from sqlalchemy import select

    key = build_cache_key(match_id, question_type, language)
    row = await session.scalar(
        select(AiChatCache).where(
            AiChatCache.cache_key == key,
            AiChatCache.expires_at > datetime.now(timezone.utc),
        )
    )
    if row:
        row.hit_count = (row.hit_count or 0) + 1
    return row


async def save_cached_response(
    session: AsyncSession,
    match: Match,
    question_type: str,
    language: str,
    response_text: str,
    *,
    tokens_input: int | None = None,
    tokens_output: int | None = None,
) -> AiChatCache:
    key = build_cache_key(match.id, question_type, language)
    expires = (match.match_date or datetime.now(timezone.utc)) + timedelta(hours=2)
    row = AiChatCache(
        cache_key=key,
        match_id=match.id,
        question_type=question_type,
        language=language,
        response_text=response_text,
        tokens_input=tokens_input,
        tokens_output=tokens_output,
        expires_at=expires,
    )
    session.add(row)
    return row


async def cleanup_expired_cache(session: AsyncSession) -> int:
    result = await session.execute(
        delete(AiChatCache).where(
            AiChatCache.expires_at < datetime.now(timezone.utc)
        )
    )
    await session.commit()
    return result.rowcount or 0
