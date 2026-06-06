"""Дедуп и snooze Telegram-алертов (Фаза 1)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.models import SourceAlertState

log = logging.getLogger("alert_cooldown")

ALERT_SNOOZE = "snooze"
ALERT_SCRAPE_ERROR = "scrape_error"
ALERT_LAYOUT = "layout"
ALERT_NO_NEW = "no_new"
ALERT_UNREACHABLE = "unreachable"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


async def _get_state(
    session: AsyncSession, source_id: int, alert_type: str
) -> SourceAlertState | None:
    return await session.get(SourceAlertState, (source_id, alert_type))


async def is_source_snoozed(session: AsyncSession, source_id: int) -> bool:
    row = await _get_state(session, source_id, ALERT_SNOOZE)
    if not row or not row.snoozed_until:
        return False
    return _aware(row.snoozed_until) > _utcnow()


async def should_send_alert(
    session: AsyncSession,
    source_id: int,
    alert_type: str,
) -> bool:
    if await is_source_snoozed(session, source_id):
        log.debug("Alert %s for source %s suppressed (snooze)", alert_type, source_id)
        return False
    row = await _get_state(session, source_id, alert_type)
    if not row or not row.last_sent_at:
        return True
    window = timedelta(hours=settings.telegram_alert_dedup_hours)
    if _utcnow() - _aware(row.last_sent_at) < window:
        log.info(
            "Alert %s for source %s suppressed (dedup %sh)",
            alert_type,
            source_id,
            settings.telegram_alert_dedup_hours,
        )
        return False
    return True


async def record_alert_sent(
    session: AsyncSession,
    source_id: int,
    alert_type: str,
) -> None:
    row = await _get_state(session, source_id, alert_type)
    now = _utcnow()
    if row:
        row.last_sent_at = now
    else:
        session.add(
            SourceAlertState(
                source_id=source_id,
                alert_type=alert_type,
                last_sent_at=now,
            )
        )
    await session.commit()


async def snooze_source(
    session: AsyncSession,
    source_id: int,
    *,
    hours: float | None = None,
) -> datetime:
    hrs = hours if hours is not None else settings.telegram_alert_snooze_hours
    until = _utcnow() + timedelta(hours=hrs)
    row = await _get_state(session, source_id, ALERT_SNOOZE)
    if row:
        row.snoozed_until = until
    else:
        session.add(
            SourceAlertState(
                source_id=source_id,
                alert_type=ALERT_SNOOZE,
                snoozed_until=until,
            )
        )
    await session.commit()
    return until
