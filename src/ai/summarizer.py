"""
Генерация AI-рекомендаций через Claude API.
Запуск: python -m src.ai.summarizer [--match-id 42]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Any, Optional

import anthropic
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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


def _build_prompt(match: Match, predictions: list[Prediction]) -> str:
    blocks = []
    for p in predictions:
        source_name = p.source.name if p.source else "unknown"
        bets_str = ", ".join(
            f"{b.bet_pick} @ {b.odds}"
            for b in sorted(p.bets, key=lambda x: x.sort_order)
            if b.bet_pick or b.odds is not None
        )
        analysis = (p.full_text or "")[:500]
        blocks.append(
            f"Source: {source_name} ({p.language})\n"
            f"Bets: {bets_str or 'n/a'}\n"
            f"Analysis: {analysis}\n---"
        )

    return f"""You are a professional sports betting analyst. Below are predictions from multiple expert tipsters for the same match.

Match: {match.team_home} vs {match.team_away}
Date: {match.match_date}
Competition: {match.competition or 'N/A'}
Sport: {match.sport or 'N/A'}

Expert Predictions:
{chr(10).join(blocks)}

Task: Write a concise consensus summary in ENGLISH (4–6 sentences):
1. What do most experts agree on?
2. The main recommended bet and odds range
3. Confidence level: High / Medium / Low
4. Any important risk factors mentioned

Important: Respond ONLY in English. Be concise and analytical, not promotional.
Return JSON only:
{{
  "summary": "...",
  "top_pick": "Over 2.5 @ ~1.80",
  "confidence": "Medium"
}}"""


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


async def _call_claude(prompt: str) -> dict[str, Any]:
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
    return _parse_json_response(text)


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

    prompt = _build_prompt(match, predictions)
    try:
        result = await _call_claude(prompt)
    except Exception as e:
        log.error("AI failed for match_id=%s: %s", match_id, e)
        await alert_ai_failed(match_id, str(e))
        raise

    match.ai_summary = result["summary"]
    match.ai_top_pick = result["top_pick"]
    match.ai_confidence = result["confidence"]
    match.ai_generated_at = datetime.utcnow()
    match.ai_model = settings.anthropic_model
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
    args = parser.parse_args()
    asyncio.run(run_summaries(match_id=args.match_id, force=args.force))


if __name__ == "__main__":
    main()
