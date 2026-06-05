"""
Telegram-бот: статус, health, логи, парсинг, add_source.
Запуск: python -m src.bot.telegram
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from src.ai.summarizer import needs_ai
from src.config import settings, setup_logging
from src.db.models import HealthCheck, Match, Prediction, ScrapeLog, Source
from src.db.session import async_session_factory
from src.scraper.diagnose import diagnose_source
from src.scraper.engine import run_scrape, run_scrape_source
from src.scraper.utils.alerter import send_message
from src.scraper.utils.browser import browser_lifecycle

log = logging.getLogger("telegram_bot")

# add_source conversation states
ASK_BASE_URL, ASK_CATEGORY, ASK_LANGUAGE, ASK_GEO = range(4)


def _effective_chat_id(update: Update) -> Optional[int]:
    if update.effective_chat:
        return update.effective_chat.id
    if update.callback_query and update.callback_query.message:
        return update.callback_query.message.chat_id
    return None


def _admin_only(update: Update) -> bool:
    admin = (settings.telegram_admin_chat_id or "").strip()
    if not admin:
        return True
    chat_id = _effective_chat_id(update)
    if chat_id is None:
        return False
    return str(chat_id) == admin


async def _deny_if_not_admin(update: Update) -> bool:
    if _admin_only(update):
        return False
    chat_id = _effective_chat_id(update)
    admin = (settings.telegram_admin_chat_id or "").strip()
    text = (
        "Access denied.\n\n"
        f"Your chat_id: <code>{chat_id}</code>\n"
        f"Configured TELEGRAM_ADMIN_CHAT_ID: <code>{admin or '(empty)'}</code>\n\n"
        "Put your chat_id into .env on the server and restart the bot."
    )
    if update.message:
        await update.message.reply_text(text, parse_mode="HTML")
    elif update.callback_query:
        await update.callback_query.message.reply_text(text, parse_mode="HTML")
    return True


async def cmd_whoami(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать chat_id без проверки admin — для настройки .env."""
    chat_id = _effective_chat_id(update)
    user = update.effective_user
    username = user.username if user else "?"
    await update.message.reply_text(
        f"chat_id: <code>{chat_id}</code>\n"
        f"username: @{username}\n\n"
        f"TELEGRAM_ADMIN_CHAT_ID in .env should be exactly:\n"
        f"<code>{chat_id}</code>",
        parse_mode="HTML",
    )


async def _on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.exception("Telegram handler error: %s", context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            f"Error: <code>{context.error}</code>", parse_mode="HTML"
        )


def _module_slug(base_url: str) -> str:
    host = urlparse(base_url).netloc.replace("www.", "")
    name = host.split(".")[0]
    return re.sub(r"[^a-z0-9]", "", name.lower()) or "source"


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _deny_if_not_admin(update):
        return
    await update.message.reply_text(
        "BetIQ Admin Bot\n\n"
        "/status — active sources\n"
        "/sources — all sources\n"
        "/health — last health checks\n"
        "/logs [N] — scrape logs\n"
        "/scrape [module] — run parser\n"
        "/diagnose [module] — Cloudflare test\n"
        "/match [slug] — match info\n"
        "/add_source — add new source\n"
        "/whoami — your chat_id for .env"
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _deny_if_not_admin(update):
        return
    async with async_session_factory() as session:
        sources = (
            await session.scalars(select(Source).where(Source.is_active.is_(True)))
        ).all()
        if not sources:
            await update.message.reply_text("No active sources.")
            return
        lines = ["<b>Active sources</b>"]
        for s in sources:
            pred_count = await session.scalar(
                select(func.count(Prediction.id)).where(Prediction.source_id == s.id)
            )
            last = (
                s.last_success_at.strftime("%Y-%m-%d %H:%M")
                if s.last_success_at
                else "never"
            )
            lines.append(
                f"• <b>{s.name}</b> ({s.scraper_module})\n"
                f"  last OK: {last} | predictions: {pred_count or 0}"
            )
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def cmd_sources(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _deny_if_not_admin(update):
        return
    async with async_session_factory() as session:
        sources = (await session.scalars(select(Source).order_by(Source.id))).all()
        lines = ["<b>Sources</b>"]
        for s in sources:
            flag = "✅" if s.is_active else "⏸"
            lines.append(
                f"{flag} id={s.id} <b>{s.name}</b> module=<code>{s.scraper_module}</code> "
                f"lang={s.language} geo={s.geo or '-'}"
            )
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def cmd_health(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _deny_if_not_admin(update):
        return
    async with async_session_factory() as session:
        sources = (await session.scalars(select(Source))).all()
        lines = ["<b>Last health checks</b>"]
        for s in sources:
            hc = await session.scalar(
                select(HealthCheck)
                .where(HealthCheck.source_id == s.id)
                .order_by(HealthCheck.checked_at.desc())
                .limit(1)
            )
            if not hc:
                lines.append(f"• {s.name}: no data")
                continue
            ok = "✅" if hc.is_accessible and hc.html_structure_ok else "❌"
            lines.append(
                f"{ok} <b>{s.name}</b> HTTP={hc.status_code} "
                f"structure={hc.html_structure_ok} "
                f"at {hc.checked_at.strftime('%m-%d %H:%M') if hc.checked_at else '-'}"
            )
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def cmd_logs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _deny_if_not_admin(update):
        return
    n = 10
    if context.args:
        try:
            n = min(int(context.args[0]), 50)
        except ValueError:
            pass
    async with async_session_factory() as session:
        logs = (
            await session.scalars(
                select(ScrapeLog).order_by(ScrapeLog.started_at.desc()).limit(n)
            )
        ).all()
        source_map = {
            s.id: s.name
            for s in (await session.scalars(select(Source))).all()
        }
        lines = [f"<b>Last {len(logs)} scrape logs</b>"]
        for lg in logs:
            name = source_map.get(lg.source_id, "?")
            err = f" — {lg.error_msg[:80]}" if lg.error_msg else ""
            lines.append(
                f"• {lg.started_at.strftime('%m-%d %H:%M') if lg.started_at else '?'} "
                f"<b>{name}</b> [{lg.status}] +{lg.items_new}/{lg.items_found}{err}"
            )
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def cmd_match(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _deny_if_not_admin(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: /match <slug>")
        return
    slug = context.args[0]
    async with async_session_factory() as session:
        match = await session.scalar(
            select(Match)
            .where(Match.slug == slug)
            .options(selectinload(Match.predictions))
        )
        if not match:
            await update.message.reply_text("Match not found.")
            return
        ai_status = "ready" if match.ai_summary else "pending"
        if needs_ai(match):
            ai_status = "needs generation"
        text = (
            f"<b>{match.team_home} vs {match.team_away}</b>\n"
            f"slug: <code>{match.slug}</code>\n"
            f"sport: {match.sport or '-'} | predictions: {match.predictions_count}\n"
            f"AI: {ai_status}\n"
        )
        if match.ai_top_pick:
            text += f"top pick: {match.ai_top_pick}\n"
        await update.message.reply_text(text, parse_mode="HTML")


async def _run_bg(coro, update: Update, started_msg: str) -> None:
    await update.message.reply_text(started_msg)

    async def wrapper():
        try:
            await coro
            await send_message(f"✅ Done: {started_msg}")
        except Exception as e:
            log.exception("Background task failed")
            await send_message(f"❌ Failed: {started_msg}\n{e}")

    asyncio.create_task(wrapper())


async def cmd_scrape(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _deny_if_not_admin(update):
        return
    module = context.args[0] if context.args else None
    label = module or "all sources"
    await _run_bg(run_scrape(source_name=module), update, f"Scrape started: {label}")


async def cmd_diagnose(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _deny_if_not_admin(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: /diagnose <scraper_module>")
        return
    module = context.args[0]

    async def job():
        async with browser_lifecycle():
            async with async_session_factory() as session:
                source = await session.scalar(
                    select(Source).where(Source.scraper_module == module)
                )
                if not source:
                    await send_message(f"Source not found: {module}")
                    return
                results = await diagnose_source(source)
                lines = [f"<b>Diagnose: {source.name}</b>"]
                for r in results:
                    ok = "✅" if r.get("ok") else "❌"
                    lines.append(
                        f"{ok} {r.get('label')}\n"
                        f"HTTP {r.get('status')} | CF={r.get('cloudflare')}\n"
                        f"H1: {r.get('h1', '')[:60]}"
                    )
                await send_message("\n".join(lines))

    await _run_bg(job(), update, f"Diagnose: {module}")


async def add_source_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await _deny_if_not_admin(update):
        return ConversationHandler.END
    context.user_data.clear()
    await update.message.reply_text(
        "Enter base URL (e.g. https://example.com):"
    )
    return ASK_BASE_URL


async def add_source_base_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    url = update.message.text.strip().rstrip("/")
    if not url.startswith("http"):
        await update.message.reply_text("URL must start with http(s). Try again:")
        return ASK_BASE_URL
    context.user_data["base_url"] = url
    await update.message.reply_text("Enter category page path (e.g. /ponturi/):")
    return ASK_CATEGORY


async def add_source_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    path = update.message.text.strip()
    if not path.startswith("/"):
        path = "/" + path
    context.user_data["category_url"] = path
    await update.message.reply_text("Content language (ro/en/ru/hu/...):")
    return ASK_LANGUAGE


async def add_source_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["language"] = update.message.text.strip().lower()[:10]
    await update.message.reply_text("GEO (RO/GB/RU/...):")
    return ASK_GEO


async def add_source_geo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    geo = update.message.text.strip().upper()[:10]
    data = context.user_data
    base_url = data["base_url"]
    module = _module_slug(base_url)
    host = urlparse(base_url).netloc

    async with async_session_factory() as session:
        existing = await session.scalar(
            select(Source).where(Source.scraper_module == module)
        )
        if existing:
            await update.message.reply_text(
                f"Module <code>{module}</code> already exists (id={existing.id}).",
                parse_mode="HTML",
            )
            return ConversationHandler.END

        source = Source(
            name=host,
            base_url=base_url,
            category_url=data["category_url"],
            language=data["language"],
            geo=geo,
            is_active=False,
            scraper_module=module,
            notes="Added via Telegram /add_source",
        )
        session.add(source)
        await session.flush()
        source_id = source.id
        module_name = module
        await session.commit()

    await update.message.reply_text(
        f"Source added (is_active=false).\n"
        f"• id: {source_id}\n"
        f"• module: <code>{module_name}</code>\n\n"
        f"Next steps:\n"
        f"1. Copy <code>src/scraper/sources/_template.py</code> → "
        f"<code>src/scraper/sources/{module_name}.py</code>\n"
        f"2. Register in <code>sources/__init__.py</code>\n"
        f"3. /diagnose {module_name}\n"
        f"4. /scrape {module_name}",
        parse_mode="HTML",
    )
    return ConversationHandler.END


async def add_source_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Cancelled.")
    return ConversationHandler.END


async def _edit_retry_result(query, text: str) -> None:
    try:
        await query.edit_message_text(text)
    except Exception:
        log.warning("Could not edit retry message, sending new one")
        await send_message(text)


async def _retry_scrape_task(
    query,
    *,
    scraper_module: str,
    source_name: str,
) -> None:
    try:
        scrape_log = await run_scrape_source(scraper_module)
        if scrape_log is None:
            await _edit_retry_result(query, f"❌ Source not found: {source_name}")
            return
        if scrape_log.status == "error":
            err = (scrape_log.error_msg or "unknown")[:400]
            await _edit_retry_result(
                query, f"❌ Retry failed: {source_name}\n{err}"
            )
        elif scrape_log.items_found == 0:
            await _edit_retry_result(
                query, f"⚠️ Retry partial: {source_name} (no articles found)"
            )
        else:
            await _edit_retry_result(
                query,
                f"✅ Retry OK: {source_name}\n"
                f"found: {scrape_log.items_found}, new: {scrape_log.items_new}",
            )
    except Exception as e:
        log.exception("Retry scrape failed for %s", source_name)
        await _edit_retry_result(query, f"❌ Retry error: {source_name}\n{e}")


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not _admin_only(update):
        await query.edit_message_text("Access denied.")
        return

    data = query.data or ""
    async with async_session_factory() as session:
        if data.startswith("scrape_retry:"):
            sid = int(data.split(":")[1])
            source = await session.get(Source, sid)
            if source and source.scraper_module:
                await query.edit_message_text(
                    f"⏳ Retrying scrape: {source.name}…"
                )
                asyncio.create_task(
                    _retry_scrape_task(
                        query,
                        scraper_module=source.scraper_module,
                        source_name=source.name,
                    )
                )
        elif data.startswith("source_disable:"):
            sid = int(data.split(":")[1])
            source = await session.get(Source, sid)
            if source:
                source.is_active = False
                await session.commit()
                await query.edit_message_text(f"Source {source.name} disabled.")


def build_app() -> Application:
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

    app = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_init(_post_init)
        .build()
    )

    conv = ConversationHandler(
        entry_points=[CommandHandler("add_source", add_source_start)],
        states={
            ASK_BASE_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_source_base_url)],
            ASK_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_source_category)],
            ASK_LANGUAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_source_language)],
            ASK_GEO: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_source_geo)],
        },
        fallbacks=[CommandHandler("cancel", add_source_cancel)],
    )

    app.add_handler(CommandHandler("whoami", cmd_whoami))
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_error_handler(_on_error)
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("sources", cmd_sources))
    app.add_handler(CommandHandler("health", cmd_health))
    app.add_handler(CommandHandler("logs", cmd_logs))
    app.add_handler(CommandHandler("match", cmd_match))
    app.add_handler(CommandHandler("scrape", cmd_scrape))
    app.add_handler(CommandHandler("diagnose", cmd_diagnose))
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(callback_handler))
    return app


async def _post_init(app: Application) -> None:
    await app.bot.delete_webhook(drop_pending_updates=True)
    me = await app.bot.get_me()
    admin = (settings.telegram_admin_chat_id or "").strip()
    log.info("Bot @%s started, admin_chat_id=%s", me.username, admin or "ANY")


def main() -> None:
    setup_logging()
    log.info("Starting Telegram bot polling")
    app = build_app()
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
