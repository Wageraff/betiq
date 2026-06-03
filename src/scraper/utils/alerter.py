"""Отправка алертов в Telegram (admin chat)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

import httpx

from src.config import settings
from src.db.models import Source

log = logging.getLogger("alerter")


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


def scrape_error_keyboard(source_id: int) -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "Retry now", "callback_data": f"scrape_retry:{source_id}"},
                {"text": "Disable source", "callback_data": f"source_disable:{source_id}"},
            ]
        ]
    }


async def alert_scrape_error(
    source: Source,
    error_msg: str,
    *,
    last_success_at: Optional[datetime] = None,
) -> None:
    text = (
        f"🔴 <b>SCRAPE ERROR</b>\n"
        f"Source: {source.name}\n"
        f"Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC\n"
        f"Error: {error_msg[:500]}\n"
        f"Last success: {_ago(last_success_at or source.last_success_at)}"
    )
    await send_message(text, reply_markup=scrape_error_keyboard(source.id))


async def alert_unreachable(source: Source, status_code: Optional[int]) -> None:
    code = status_code if status_code is not None else "?"
    await send_message(f"🔴 [{source.name}] Site unreachable ({code})")


async def alert_layout_changed(source: Source) -> None:
    await send_message(
        f"🔧 [{source.name}] Layout changed — selectors not found"
    )


async def alert_no_new_predictions(source: Source) -> None:
    await send_message(
        f"📭 [{source.name}] No new predictions in 24h"
    )


async def alert_ai_failed(match_id: int, error: str) -> None:
    await send_message(
        f"🤖 AI summary failed for match_id={match_id}: {error[:300]}"
    )


async def alert_scrape_warning(source: Source, error_msg: str) -> None:
    await send_message(f"⚠️ [{source.name}] Scrape failed: {error_msg[:400]}")
