"""Утренняя сводка в Telegram."""
from __future__ import annotations

import logging

from src.bot.formatters import build_digest_text
from src.db.session import async_session_factory
from src.scraper.utils.alerter import send_message

log = logging.getLogger("telegram_digest")


async def send_morning_digest() -> bool:
    async with async_session_factory() as session:
        text = await build_digest_text(session)
    ok = await send_message(text)
    if ok:
        log.info("Morning digest sent")
    else:
        log.warning("Morning digest not sent (Telegram not configured?)")
    return ok
