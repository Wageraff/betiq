"""
Telegram-бот: дашборд, меню, парсинг, AI, сервисные команды.
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

from src.ai.summarizer import _matches_needing_ai, generate_for_match, needs_ai
from src.bot.digest import send_morning_digest
from src.bot.formatters import (
    build_dashboard_text,
    build_digest_text,
    build_log_info_text,
    build_logs_text,
    read_log_tail,
    split_telegram_messages,
)
from src.bot.keyboards import (
    MENU_AI,
    MENU_BUTTONS,
    MENU_DASHBOARD,
    MENU_DIAGNOSE,
    MENU_HELP,
    MENU_LOGS,
    MENU_SCRAPE,
    MENU_SERVICE,
    MENU_SOURCES,
    ai_matches_keyboard,
    main_menu_keyboard,
    service_inline_keyboard,
    sources_inline_keyboard,
)
from src.config import settings, setup_logging
from src.db.models import HealthCheck, Match, Prediction, ScrapeLog, Source
from src.db.session import async_session_factory
from src.scraper.diagnose import diagnose_source
from src.scraper.engine import run_scrape, run_scrape_source
from src.scraper.health_check import run_health_checks
from src.scraper.utils.alert_cooldown import snooze_source
from src.scraper.utils.alerter import send_message
from src.scraper.utils.browser import browser_lifecycle

log = logging.getLogger("telegram_bot")

ASK_BASE_URL, ASK_CATEGORY, ASK_LANGUAGE, ASK_GEO = range(4)

HELP_TEXT = (
    "<b>BetIQ Admin Bot</b>\n\n"
    "Используйте кнопки меню или команды:\n"
    "/dashboard — сводка по источникам\n"
    "/digest — утренняя сводка\n"
    "/sources — все источники\n"
    "/health — health checks\n"
    "/logs [N|errors|module] — scrape logs\n"
    "/scrape [module] — парсинг\n"
    "/diagnose [module] — Cloudflare test\n"
    "/ai [match_id|list] — AI summaries\n"
    "/match &lt;slug&gt; — карточка матча\n"
    "/loginfo — размер app.log\n"
    "/logtail [N] — последние строки лога\n"
    "/repair — repair catalog\n"
    "/health_run — health check сейчас\n"
    "/add_source — новый источник\n"
    "/menu — обновить клавиатуру\n\n"
    "На алертах: Retry, Diagnose, Logs, Snooze, Disable/Enable"
)


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


async def _reply_html(
    update: Update,
    text: str,
    *,
    reply_markup=None,
) -> None:
    if not update.message:
        return
    parts = split_telegram_messages(text)
    km = reply_markup or main_menu_keyboard()
    for i, part in enumerate(parts):
        await update.message.reply_text(
            part,
            parse_mode="HTML",
            reply_markup=km if i == len(parts) - 1 else None,
        )


async def cmd_whoami(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
        HELP_TEXT,
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _deny_if_not_admin(update):
        return
    await update.message.reply_text(
        "Меню обновлено 👇",
        reply_markup=main_menu_keyboard(),
    )


async def cmd_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _deny_if_not_admin(update):
        return
    async with async_session_factory() as session:
        text = await build_dashboard_text(session)
    await _reply_html(update, text)


async def cmd_digest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _deny_if_not_admin(update):
        return
    async with async_session_factory() as session:
        text = await build_digest_text(session)
    await _reply_html(update, text)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _deny_if_not_admin(update):
        return
    async with async_session_factory() as session:
        sources = (
            await session.scalars(select(Source).where(Source.is_active.is_(True)))
        ).all()
        if not sources:
            await _reply_html(update, "No active sources.")
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
        await _reply_html(update, "\n".join(lines))


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
        await _reply_html(update, "\n".join(lines))


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
        await _reply_html(update, "\n".join(lines))


def _parse_logs_args(args: list[str]) -> tuple[int, str | None, bool]:
    limit = 10
    module: str | None = None
    errors_only = False
    for arg in args:
        low = arg.lower()
        if low == "errors":
            errors_only = True
        elif low.isdigit():
            limit = min(int(low), 50)
        else:
            module = arg
    return limit, module, errors_only


async def cmd_logs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _deny_if_not_admin(update):
        return
    limit, module, errors_only = _parse_logs_args(context.args or [])
    async with async_session_factory() as session:
        text = await build_logs_text(
            session, limit=limit, module=module, errors_only=errors_only
        )
    await _reply_html(update, text)


async def cmd_loginfo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _deny_if_not_admin(update):
        return
    await _reply_html(update, build_log_info_text())


async def cmd_logtail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _deny_if_not_admin(update):
        return
    n = 40
    if context.args:
        try:
            n = int(context.args[0])
        except ValueError:
            pass
    await _reply_html(update, read_log_tail(lines_count=n))


async def cmd_match(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _deny_if_not_admin(update):
        return
    if not context.args:
        await _reply_html(update, "Usage: /match &lt;slug&gt;")
        return
    slug = context.args[0]
    async with async_session_factory() as session:
        match = await session.scalar(
            select(Match)
            .where(Match.slug == slug)
            .options(selectinload(Match.predictions))
        )
        if not match:
            await _reply_html(update, "Match not found.")
            return
        ai_status = "ready" if match.ai_summary else "pending"
        if needs_ai(match):
            ai_status = "needs generation"
        text = (
            f"<b>{match.team_home} vs {match.team_away}</b>\n"
            f"id: {match.id} | slug: <code>{match.slug}</code>\n"
            f"sport: {match.sport or '-'} | predictions: {match.predictions_count}\n"
            f"AI: {ai_status}\n"
        )
        if match.ai_top_pick:
            text += f"top pick: {match.ai_top_pick}\n"
        if match.ai_summary:
            summary = match.ai_summary[:500]
            if len(match.ai_summary) > 500:
                summary += "…"
            text += f"\n{summary}"
        await _reply_html(update, text)


async def _run_bg(coro, update: Update, started_msg: str) -> None:
    await update.message.reply_text(started_msg, reply_markup=main_menu_keyboard())

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
    label = module or "all active sources"
    await _run_bg(run_scrape(source_name=module), update, f"Scrape: {label}")


async def cmd_diagnose(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _deny_if_not_admin(update):
        return
    if not context.args:
        async with async_session_factory() as session:
            sources = (
                await session.scalars(
                    select(Source).where(Source.is_active.is_(True))
                )
            ).all()
        await update.message.reply_text(
            "Выберите источник:",
            reply_markup=sources_inline_keyboard(
                list(sources), prefix="menu:diagnose", show_all=False
            ),
        )
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


async def cmd_health_run(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _deny_if_not_admin(update):
        return
    module = context.args[0] if context.args else None
    label = module or "all active"
    await _run_bg(run_health_checks(module), update, f"Health check: {label}")


async def cmd_repair(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _deny_if_not_admin(update):
        return

    async def job():
        from src.db.repair_catalog import run_repair_catalog

        stats = await run_repair_catalog()
        await send_message(f"<b>Repair catalog done</b>\n<code>{stats}</code>")

    await _run_bg(job(), update, "Repair catalog")


async def cmd_ai(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _deny_if_not_admin(update):
        return

    if context.args:
        arg = context.args[0]
        if arg.isdigit():
            match_id = int(arg)

            async def job():
                async with async_session_factory() as session:
                    ok = await generate_for_match(session, match_id, force=True)
                if ok:
                    await send_message(f"✅ AI generated for match {match_id}")
                else:
                    await send_message(f"⚠️ AI skipped for match {match_id}")

            await _run_bg(job(), update, f"AI summary: match {match_id}")
            return

    async with async_session_factory() as session:
        ids = await _matches_needing_ai(session)
        if not ids:
            await _reply_html(update, "✅ All matches with 2+ predictions have up-to-date AI.")
            return
        matches = (
            await session.scalars(
                select(Match).where(Match.id.in_(ids[:10])).order_by(Match.match_date.desc())
            )
        ).all()
        lines = [f"<b>AI queue</b> ({len(ids)} total, top 10):"]
        for m in matches:
            lines.append(
                f"• {m.id}: <b>{m.team_home} vs {m.team_away}</b> "
                f"({m.predictions_count} preds)"
            )
        lines.append("\nTap a match or: /ai &lt;match_id&gt;")
        await update.message.reply_text(
            "\n".join(lines),
            parse_mode="HTML",
            reply_markup=ai_matches_keyboard(list(matches)),
        )


async def menu_message_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if await _deny_if_not_admin(update):
        return
    text = (update.message.text or "").strip()
    if text not in MENU_BUTTONS:
        return

    if text == MENU_DASHBOARD:
        await cmd_dashboard(update, context)
    elif text == MENU_SOURCES:
        await cmd_sources(update, context)
    elif text == MENU_LOGS:
        context.args = ["10"]
        await cmd_logs(update, context)
    elif text == MENU_DIAGNOSE:
        context.args = []
        await cmd_diagnose(update, context)
    elif text == MENU_SCRAPE:
        async with async_session_factory() as session:
            sources = (
                await session.scalars(
                    select(Source).where(Source.is_active.is_(True))
                )
            ).all()
        await update.message.reply_text(
            "Запустить парсинг:",
            reply_markup=sources_inline_keyboard(list(sources), prefix="menu:scrape"),
        )
    elif text == MENU_AI:
        context.args = []
        await cmd_ai(update, context)
    elif text == MENU_SERVICE:
        await update.message.reply_text(
            "Сервисные действия:",
            reply_markup=service_inline_keyboard(),
        )
    elif text == MENU_HELP:
        await cmd_start(update, context)


async def add_source_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await _deny_if_not_admin(update):
        return ConversationHandler.END
    context.user_data.clear()
    await update.message.reply_text("Enter base URL (e.g. https://example.com):")
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
        f"Next: /diagnose {module_name} → /scrape {module_name}",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )
    return ConversationHandler.END


async def add_source_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Cancelled.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


async def _edit_retry_result(query, text: str, *, parse_mode: str | None = None) -> None:
    try:
        await query.edit_message_text(text, parse_mode=parse_mode)
    except Exception:
        log.warning("Could not edit message, sending new one")
        await send_message(text)


def _format_scrape_logs(logs: list[ScrapeLog], source_name: str) -> str:
    if not logs:
        return f"<b>{source_name}</b>: no scrape logs yet."
    lines = [f"<b>Last {len(logs)} logs: {source_name}</b>"]
    for lg in logs:
        err = f"\n  {lg.error_msg[:120]}" if lg.error_msg else ""
        ts = lg.started_at.strftime("%m-%d %H:%M") if lg.started_at else "?"
        lines.append(
            f"• {ts} [{lg.status}] +{lg.items_new}/{lg.items_found}{err}"
        )
    return "\n".join(lines)


async def _diagnose_task(query, *, source: Source) -> None:
    try:
        async with browser_lifecycle():
            async with async_session_factory() as session:
                src = await session.get(Source, source.id)
                if not src or not src.scraper_module:
                    await _edit_retry_result(query, f"❌ Source not found: {source.name}")
                    return
                results = await diagnose_source(src)
                lines = [f"<b>Diagnose: {src.name}</b>"]
                for r in results:
                    ok = "✅" if r.get("ok") else "❌"
                    lines.append(
                        f"{ok} {r.get('label')}\n"
                        f"HTTP {r.get('status')} | CF={r.get('cloudflare')}\n"
                        f"H1: {r.get('h1', '')[:60]}"
                    )
                await _edit_retry_result(query, "\n".join(lines))
    except Exception as e:
        log.exception("Diagnose callback failed for %s", source.name)
        await _edit_retry_result(query, f"❌ Diagnose error: {source.name}\n{e}")


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
            await _edit_retry_result(query, f"❌ Retry failed: {source_name}\n{err}")
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


async def _menu_callback(query, data: str) -> None:
    """menu:scrape:mod | menu:diagnose:mod | menu:ai:id | menu:service:action"""
    parts = data.split(":")
    if len(parts) < 3:
        return
    _, section, arg = parts[0], parts[1], ":".join(parts[2:])

    if section == "scrape":
        label = arg if arg != "all" else "all active"
        await query.edit_message_text(f"⏳ Scrape started: {label}…")

        async def job():
            try:
                await run_scrape(source_name=None if arg == "all" else arg)
                await send_message(f"✅ Scrape done: {label}")
            except Exception as e:
                await send_message(f"❌ Scrape failed: {label}\n{e}")

        asyncio.create_task(job())

    elif section == "diagnose":
        async with async_session_factory() as session:
            source = await session.scalar(
                select(Source).where(Source.scraper_module == arg)
            )
        if not source:
            await query.edit_message_text(f"Source not found: {arg}")
            return
        await query.edit_message_text(f"⏳ Diagnose: {source.name}…")
        asyncio.create_task(_diagnose_task(query, source=source))

    elif section == "ai":
        try:
            match_id = int(arg)
        except ValueError:
            return
        await query.edit_message_text(f"⏳ AI summary for match {match_id}…")

        async def ai_job():
            try:
                async with async_session_factory() as session:
                    ok = await generate_for_match(session, match_id, force=True)
                if ok:
                    await _edit_retry_result(
                        query, f"✅ AI generated for match {match_id}"
                    )
                else:
                    await _edit_retry_result(
                        query, f"⚠️ AI skipped for match {match_id}"
                    )
            except Exception as e:
                await _edit_retry_result(query, f"❌ AI failed: {e}")

        asyncio.create_task(ai_job())

    elif section == "service":
        if arg == "health":
            await query.edit_message_text("⏳ Health check running…")

            async def hjob():
                try:
                    n = await run_health_checks()
                    await send_message(f"✅ Health check done ({n} sources)")
                except Exception as e:
                    await send_message(f"❌ Health check failed: {e}")

            asyncio.create_task(hjob())

        elif arg == "repair":
            await query.edit_message_text("⏳ Repair catalog running…")

            async def rjob():
                try:
                    from src.db.repair_catalog import run_repair_catalog

                    stats = await run_repair_catalog()
                    await send_message(f"✅ Repair done\n<code>{stats}</code>")
                except Exception as e:
                    await send_message(f"❌ Repair failed: {e}")

            asyncio.create_task(rjob())

        elif arg == "loginfo":
            await query.edit_message_text(build_log_info_text(), parse_mode="HTML")

        elif arg == "logtail":
            text = read_log_tail(lines_count=40)
            for part in split_telegram_messages(text):
                await send_message(part)

        elif arg == "digest":
            async with async_session_factory() as session:
                text = await build_digest_text(session)
            await query.edit_message_text(text, parse_mode="HTML")


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not _admin_only(update):
        await query.edit_message_text("Access denied.")
        return

    data = query.data or ""

    if data.startswith("menu:"):
        await _menu_callback(query, data)
        return

    if ":" not in data:
        return
    action, sid_raw = data.split(":", 1)
    try:
        sid = int(sid_raw)
    except ValueError:
        return

    async with async_session_factory() as session:
        source = await session.get(Source, sid)

        if action == "scrape_retry":
            if source and source.scraper_module:
                await query.edit_message_text(f"⏳ Retrying scrape: {source.name}…")
                asyncio.create_task(
                    _retry_scrape_task(
                        query,
                        scraper_module=source.scraper_module,
                        source_name=source.name,
                    )
                )

        elif action == "scrape_diagnose":
            if source:
                await query.edit_message_text(f"⏳ Diagnose: {source.name}…")
                asyncio.create_task(_diagnose_task(query, source=source))

        elif action == "scrape_logs":
            if source:
                logs = (
                    await session.scalars(
                        select(ScrapeLog)
                        .where(ScrapeLog.source_id == source.id)
                        .order_by(ScrapeLog.started_at.desc())
                        .limit(5)
                    )
                ).all()
                text = _format_scrape_logs(list(logs), source.name)
                await query.edit_message_text(text, parse_mode="HTML")

        elif action == "source_snooze":
            if source:
                until = await snooze_source(session, source.id)
                until_s = until.strftime("%Y-%m-%d %H:%M UTC")
                await query.edit_message_text(
                    f"🔕 Alerts snoozed for <b>{source.name}</b> until {until_s}",
                    parse_mode="HTML",
                )

        elif action == "source_disable":
            if source:
                source.is_active = False
                await session.commit()
                await query.edit_message_text(
                    f"⏸ Source <b>{source.name}</b> disabled.",
                    parse_mode="HTML",
                )

        elif action == "source_enable":
            if source:
                source.is_active = True
                await session.commit()
                await query.edit_message_text(
                    f"✅ Source <b>{source.name}</b> enabled.",
                    parse_mode="HTML",
                )


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
            ASK_BASE_URL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_source_base_url)
            ],
            ASK_CATEGORY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_source_category)
            ],
            ASK_LANGUAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_source_language)
            ],
            ASK_GEO: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_source_geo)],
        },
        fallbacks=[CommandHandler("cancel", add_source_cancel)],
    )

    app.add_handler(CommandHandler("whoami", cmd_whoami))
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("dashboard", cmd_dashboard))
    app.add_handler(CommandHandler("digest", cmd_digest))
    app.add_error_handler(_on_error)
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("sources", cmd_sources))
    app.add_handler(CommandHandler("health", cmd_health))
    app.add_handler(CommandHandler("health_run", cmd_health_run))
    app.add_handler(CommandHandler("logs", cmd_logs))
    app.add_handler(CommandHandler("loginfo", cmd_loginfo))
    app.add_handler(CommandHandler("logtail", cmd_logtail))
    app.add_handler(CommandHandler("repair", cmd_repair))
    app.add_handler(CommandHandler("match", cmd_match))
    app.add_handler(CommandHandler("scrape", cmd_scrape))
    app.add_handler(CommandHandler("diagnose", cmd_diagnose))
    app.add_handler(CommandHandler("ai", cmd_ai))
    app.add_handler(conv)
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.Regex(
                "^(" + "|".join(re.escape(b) for b in MENU_BUTTONS) + ")$"
            ),
            menu_message_handler,
        )
    )
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
