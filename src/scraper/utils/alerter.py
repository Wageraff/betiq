"""Отправка алертов в Telegram (admin chat)."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional, Protocol

import httpx

from src.config import settings
from src.db.session import async_session_factory
from src.scraper.utils.alert_cooldown import (
    ALERT_LAYOUT,
    ALERT_NO_NEW,
    ALERT_SCRAPE_ERROR,
    ALERT_UNREACHABLE,
    record_alert_sent,
    should_send_alert,
)

log = logging.getLogger("alerter")


class _SourceLike(Protocol):
    id: int
    name: str
    is_active: bool


async def send_message(
    text: str,
    *,
    reply_markup: Optional[dict[str, Any]] = None,
    parse_mode: str = "HTML",
) -> bool:
    token = settings.telegram_bot_token
    chat_id = settings.telegram_admin_chat_id
    if not token or not chat_id:
        log.debug("Telegram not configured, skip alert")
        return False

    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
        return True
    except Exception as e:
        log.error("Failed to send Telegram alert: %s", e)
        return False


def _ago(dt: Optional[datetime]) -> str:
    if not dt:
        return "never"
    delta = datetime.utcnow() - dt.replace(tzinfo=None) if dt.tzinfo else datetime.utcnow() - dt
    hours = int(delta.total_seconds() // 3600)
    if hours < 1:
        return f"{int(delta.total_seconds() // 60)}m ago"
    if hours < 48:
        return f"{hours}h ago"
    return f"{delta.days}d ago"


def _is_active(source: _SourceLike) -> bool:
    return bool(getattr(source, "is_active", True))


def source_action_keyboard(
    source_id: int,
    *,
    show_retry: bool = False,
    is_active: bool = True,
) -> dict:
    rows: list[list[dict[str, str]]] = []
    row1: list[dict[str, str]] = []
    if show_retry:
        row1.append({"text": "Retry now", "callback_data": f"scrape_retry:{source_id}"})
    row1.append({"text": "Diagnose", "callback_data": f"scrape_diagnose:{source_id}"})
    rows.append(row1)
    rows.append(
        [
            {"text": "Logs (5)", "callback_data": f"scrape_logs:{source_id}"},
            {
                "text": f"Snooze {int(settings.telegram_alert_snooze_hours)}h",
                "callback_data": f"source_snooze:{source_id}",
            },
        ]
    )
    if is_active:
        rows.append(
            [{"text": "Disable source", "callback_data": f"source_disable:{source_id}"}]
        )
    else:
        rows.append(
            [{"text": "Enable source", "callback_data": f"source_enable:{source_id}"}]
        )
    return {"inline_keyboard": rows}


def scrape_error_keyboard(source_id: int, *, is_active: bool = True) -> dict:
    return source_action_keyboard(
        source_id, show_retry=True, is_active=is_active
    )


async def _alert_source(
    source: _SourceLike,
    alert_type: str,
    text: str,
    *,
    show_retry: bool = False,
) -> None:
    async with async_session_factory() as session:
        if not await should_send_alert(session, source.id, alert_type):
            return
        markup = source_action_keyboard(
            source.id,
            show_retry=show_retry,
            is_active=_is_active(source),
        )
        if await send_message(text, reply_markup=markup):
            await record_alert_sent(session, source.id, alert_type)


async def alert_scrape_error(
    source: _SourceLike,
    error_msg: str,
    *,
    last_success_at: Optional[datetime] = None,
) -> None:
    last_ok = last_success_at
    if last_ok is None:
        last_ok = getattr(source, "last_success_at", None)
    text = (
        f"🔴 <b>SCRAPE ERROR</b>\n"
        f"Source: {source.name}\n"
        f"Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC\n"
        f"Error: {error_msg[:500]}\n"
        f"Last success: {_ago(last_ok)}"
    )
    await _alert_source(source, ALERT_SCRAPE_ERROR, text, show_retry=True)


async def alert_unreachable(source: _SourceLike, status_code: Optional[int]) -> None:
    code = status_code if status_code is not None else "?"
    text = f"🔴 <b>Site unreachable</b>\nSource: {source.name}\nHTTP: {code}"
    await _alert_source(source, ALERT_UNREACHABLE, text)


async def alert_layout_changed(source: _SourceLike) -> None:
    text = (
        f"🔧 <b>Layout changed</b>\n"
        f"Source: {source.name}\n"
        f"Selectors not found on listing page"
    )
    await _alert_source(source, ALERT_LAYOUT, text, show_retry=True)


async def alert_no_new_predictions(source: _SourceLike) -> None:
    text = (
        f"📭 <b>No new predictions</b>\n"
        f"Source: {source.name}\n"
        f"No items_new in the last 24h"
    )
    await _alert_source(source, ALERT_NO_NEW, text, show_retry=True)


async def alert_ai_failed(match_id: int, error: str) -> None:
    await send_message(
        f"🤖 AI summary failed for match_id={match_id}: {error[:300]}"
    )


async def alert_scrape_warning(source: _SourceLike, error_msg: str) -> None:
    await send_message(f"⚠️ [{source.name}] Scrape failed: {error_msg[:400]}")
