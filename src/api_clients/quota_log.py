"""Логирование квот API и времени последнего odds-синка по sport_key."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.models import ApiQuotaSnapshot, OddsSyncLog
from src.db.session import async_session_factory

log = logging.getLogger("quota_log")

_last_quota_alert_at: dict[str, datetime] = {}


async def save_quota_snapshot(
    provider: str,
    remaining: int | None,
    used: int | None,
    *,
    session: AsyncSession | None = None,
) -> None:
    if remaining is None and used is None:
        return

    async def _write(db: AsyncSession) -> None:
        db.add(
            ApiQuotaSnapshot(
                provider=provider,
                requests_remaining=remaining,
                requests_used=used,
            )
        )
        await db.commit()

    if session is not None:
        session.add(
            ApiQuotaSnapshot(
                provider=provider,
                requests_remaining=remaining,
                requests_used=used,
            )
        )
        return

    async with async_session_factory() as db:
        await _write(db)

    if (
        provider == "the_odds_api"
        and remaining is not None
        and remaining < settings.api_quota_alert_threshold
    ):
        await _maybe_alert_low_quota(provider, remaining)


async def _maybe_alert_low_quota(provider: str, remaining: int) -> None:
    now = datetime.now(timezone.utc)
    last = _last_quota_alert_at.get(provider)
    if last and (now - last).total_seconds() < 3600:
        return
    _last_quota_alert_at[provider] = now
    try:
        from src.scraper.utils.alerter import send_message

        await send_message(
            f"⚠️ <b>{provider}</b>: осталось <b>{remaining}</b> запросов"
        )
    except Exception:
        log.exception("Quota alert failed")


async def get_last_odds_sync(
    session: AsyncSession, sport_key: str
) -> datetime | None:
    row = await session.get(OddsSyncLog, sport_key)
    return row.synced_at if row else None


async def record_odds_sync(session: AsyncSession, sport_key: str) -> None:
    now = datetime.now(timezone.utc)
    row = await session.get(OddsSyncLog, sport_key)
    if row:
        row.synced_at = now
    else:
        session.add(OddsSyncLog(sport_key=sport_key, synced_at=now))


async def latest_quota_snapshots(
    session: AsyncSession,
) -> dict[str, ApiQuotaSnapshot | None]:
    out: dict[str, ApiQuotaSnapshot | None] = {}
    for provider in ("the_odds_api", "api_football"):
        row = await session.scalar(
            select(ApiQuotaSnapshot)
            .where(ApiQuotaSnapshot.provider == provider)
            .order_by(ApiQuotaSnapshot.recorded_at.desc())
            .limit(1)
        )
        out[provider] = row
    return out
