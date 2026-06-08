"""
Генерация AI-рекомендаций через Claude API.
Запуск: python -m src.ai.summarizer [--match-id 42]
Шаблон промпта: prompts/ai_match_summary.txt (настройка в config.ini [ai]).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
from datetime import datetime
from typing import Any, Optional

import anthropic
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.ai.prompt_template import build_match_summary_prompt, resolve_prompt_path
from src.config import settings, setup_logging
from src.scraper.utils.alerter import alert_ai_failed
from src.db.models import Match, Prediction
from src.db.session import async_session_factory

log = logging.getLogger("summarizer")


def needs_ai(match: Match) -> bool:
    if (match.predictions_count or 0) < 2:
        return False
    if match.ai_generated_at is None:
        return True
    updated = match.updated_at
    generated = match.ai_generated_at
    if updated is None:
        return True
    if generated is None:
        return True
    return updated > generated


def _parse_json_response(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("No JSON object in Claude response")
    data = json.loads(match.group())
    for key in ("summary", "top_pick", "confidence"):
        if key not in data:
            raise ValueError(f"Missing field: {key}")
    return data


async def _call_claude(prompt: str) -> tuple[dict[str, Any], int, int]:
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")

    model = settings.anthropic_model
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    message = await client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(block.text for block in message.content if block.type == "text")
    usage = getattr(message, "usage", None)
    inp = int(getattr(usage, "input_tokens", 0) or 0)
    out = int(getattr(usage, "output_tokens", 0) or 0)
    return _parse_json_response(text), inp, out


async def _load_match(session: AsyncSession, match_id: int) -> Optional[Match]:
    return await session.scalar(
        select(Match)
        .where(Match.id == match_id)
        .options(
            selectinload(Match.predictions).selectinload(Prediction.bets),
            selectinload(Match.predictions).selectinload(Prediction.source),
        )
    )


async def generate_for_match(
    session: AsyncSession,
    match_id: int,
    *,
    force: bool = False,
) -> bool:
    match = await _load_match(session, match_id)
    if not match:
        log.warning("Match %s not found", match_id)
        return False

    if not force and not needs_ai(match):
        log.debug("Match %s does not need AI update", match_id)
        return False

    predictions = [p for p in match.predictions if p.match_id == match.id]
    if len(predictions) < 2:
        log.warning("Match %s has fewer than 2 predictions", match_id)
        return False

    prompt = build_match_summary_prompt(match, predictions)
    try:
        result, input_tokens, output_tokens = await _call_claude(prompt)
    except Exception as e:
        log.error("AI failed for match_id=%s: %s", match_id, e)
        await alert_ai_failed(match_id, str(e))
        raise

    from src.ai.usage_log import record_ai_usage

    match.ai_summary = result["summary"]
    match.ai_top_pick = result["top_pick"]
    match.ai_confidence = result["confidence"]
    match.ai_generated_at = datetime.utcnow()
    match.ai_model = settings.anthropic_model
    await record_ai_usage(
        session,
        match_id=match.id,
        model=settings.anthropic_model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    await session.commit()
    log.info("AI summary generated for match %s (%s)", match_id, match.slug)
    return True


async def _matches_needing_ai(session: AsyncSession) -> list[int]:
    stmt = select(Match.id).where(Match.predictions_count >= 2)
    stmt = stmt.where(
        or_(
            Match.ai_generated_at.is_(None),
            Match.updated_at > Match.ai_generated_at,
        )
    )
    return list((await session.scalars(stmt)).all())


async def print_prompt_for_match(match_id: int) -> None:
    async with async_session_factory() as session:
        match = await _load_match(session, match_id)
        if not match:
            log.error("Match %s not found", match_id)
            sys.exit(1)
        predictions = [p for p in match.predictions if p.match_id == match.id]
        prompt = build_match_summary_prompt(match, predictions)
        print(f"# Template: {resolve_prompt_path()}\n")
        print(prompt)


async def run_summaries(
    match_id: Optional[int] = None,
    *,
    force: bool = False,
) -> int:
    generated = 0
    async with async_session_factory() as session:
        ids = [match_id] if match_id else await _matches_needing_ai(session)

        for mid in ids:
            try:
                if await generate_for_match(session, mid, force=force):
                    generated += 1
            except Exception:
                await session.rollback()

    log.info("Generated %s AI summaries", generated)
    return generated


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(description="Generate AI match summaries")
    parser.add_argument("--match-id", type=int, help="Single match ID")
    parser.add_argument("--force", action="store_true", help="Regenerate even if up to date")
    parser.add_argument(
        "--print-prompt",
        action="store_true",
        help="Print rendered prompt (requires --match-id), no API call",
    )
    args = parser.parse_args()

    if args.print_prompt:
        if not args.match_id:
            parser.error("--print-prompt requires --match-id")
        asyncio.run(print_prompt_for_match(args.match_id))
        return

    asyncio.run(run_summaries(match_id=args.match_id, force=args.force))


if __name__ == "__main__":
    main()
