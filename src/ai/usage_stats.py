"""Статистика расхода Claude API для админки."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.models import AiUsageLog, Match

log = logging.getLogger("ai_usage")


@dataclass
class DayUsage:
    day: date
    requests: int
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    official_cost_usd: float | None = None


def _utc_day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    return start, end


def estimate_cost_usd(
    input_tokens: int, output_tokens: int, *, model: str | None = None
) -> float:
    """Оценка по тарифам из config.ini (USD за 1M токенов)."""
    _ = model
    inp_m = max(0, input_tokens) / 1_000_000
    out_m = max(0, output_tokens) / 1_000_000
    return round(
        inp_m * settings.ai_input_price_per_mtok
        + out_m * settings.ai_output_price_per_mtok,
        4,
    )


async def _usage_from_log(
    session: AsyncSession, day: date
) -> tuple[int, int, int]:
    since, until = _utc_day_bounds(day)
    row = (
        await session.execute(
            select(
                func.count(),
                func.coalesce(func.sum(AiUsageLog.input_tokens), 0),
                func.coalesce(func.sum(AiUsageLog.output_tokens), 0),
            ).where(
                AiUsageLog.created_at >= since,
                AiUsageLog.created_at < until,
            )
        )
    ).one()
    return int(row[0]), int(row[1]), int(row[2])


async def _summaries_from_matches(session: AsyncSession, day: date) -> int:
    """Сколько сводок сгенерировано в этот день (fallback до ai_usage_log)."""
    since, until = _utc_day_bounds(day)
    return int(
        await session.scalar(
            select(func.count()).where(
                Match.ai_generated_at.isnot(None),
                Match.ai_generated_at >= since,
                Match.ai_generated_at < until,
            )
        )
        or 0
    )


async def day_usage(session: AsyncSession, day: date) -> DayUsage:
    requests, inp, out = await _usage_from_log(session, day)
    if requests == 0:
        legacy = await _summaries_from_matches(session, day)
        if legacy:
            requests = legacy
    cost = estimate_cost_usd(inp, out)
    return DayUsage(
        day=day,
        requests=requests,
        input_tokens=inp,
        output_tokens=out,
        estimated_cost_usd=cost,
    )


async def fetch_admin_daily_costs(
    days: int = 3,
) -> dict[date, float]:
    """Официальные расходы USD из Anthropic Admin API (нужен ANTHROPIC_ADMIN_API_KEY)."""
    admin_key = settings.anthropic_admin_api_key
    if not admin_key:
        return {}

    end = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    start = end - timedelta(days=days)
    params = {
        "starting_at": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ending_at": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "bucket_width": "1d",
        "limit": min(days, 31),
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                "https://api.anthropic.com/v1/organizations/cost_report",
                headers={
                    "x-api-key": admin_key,
                    "anthropic-version": "2023-06-01",
                },
                params=params,
            )
            if resp.status_code == 401:
                log.warning("Anthropic Admin API: unauthorized")
                return {}
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        log.exception("Anthropic Admin API cost_report failed")
        return {}

    out: dict[date, float] = {}
    for bucket in data.get("data") or []:
        starting = bucket.get("starting_at") or bucket.get("ending_at")
        if not starting:
            continue
        try:
            d = datetime.fromisoformat(starting.replace("Z", "+00:00")).date()
        except ValueError:
            continue
        cents = 0.0
        for item in bucket.get("results") or []:
            try:
                cents += float(item.get("amount") or 0)
            except (TypeError, ValueError):
                continue
        out[d] = round(cents / 100.0, 4)
    return out


async def build_ai_usage_report(session: AsyncSession) -> dict[str, Any]:
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)

    today_u = await day_usage(session, today)
    yesterday_u = await day_usage(session, yesterday)

    admin_error: str | None = None
    official: dict[date, float] = {}
    if settings.anthropic_admin_api_key:
        official = await fetch_admin_daily_costs(days=3)
    elif settings.anthropic_api_key:
        admin_error = (
            "Для точных расходов в USD добавьте ANTHROPIC_ADMIN_API_KEY в .env "
            "(ключ sk-ant-admin-… из Console → Settings → Admin API)."
        )

    if today in official:
        today_u.official_cost_usd = official[today]
    if yesterday in official:
        yesterday_u.official_cost_usd = official[yesterday]

    budget = settings.ai_daily_budget_usd
    today_spend = (
        today_u.official_cost_usd
        if today_u.official_cost_usd is not None
        else today_u.estimated_cost_usd
    )
    remaining = round(budget - today_spend, 4) if budget > 0 else None

    return {
        "configured": bool(settings.anthropic_api_key),
        "admin_api_configured": bool(settings.anthropic_admin_api_key),
        "model": settings.anthropic_model,
        "daily_budget_usd": budget if budget > 0 else None,
        "max_summaries_per_day": (
            settings.ai_max_summaries_per_day
            if settings.ai_max_summaries_per_day > 0
            else None
        ),
        "pricing_note": (
            f"Оценка: ${settings.ai_input_price_per_mtok}/M in, "
            f"${settings.ai_output_price_per_mtok}/M out"
        ),
        "admin_error": admin_error,
        "today": _day_to_dict(today_u),
        "yesterday": _day_to_dict(yesterday_u),
        "remaining_budget_usd": remaining,
        "timezone": "UTC",
        "checked_at": datetime.now(timezone.utc),
    }


def _day_to_dict(d: DayUsage) -> dict[str, Any]:
    return {
        "date": d.day.isoformat(),
        "requests": d.requests,
        "input_tokens": d.input_tokens,
        "output_tokens": d.output_tokens,
        "estimated_cost_usd": d.estimated_cost_usd,
        "official_cost_usd": d.official_cost_usd,
    }
