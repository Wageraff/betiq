"""Тексты для Telegram: dashboard, логи, digest."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.summarizer import _matches_needing_ai
import html

from src.api.admin.app_log import app_log_info, resolve_app_log_path
from src.config import settings
from src.db.models import Match, ScrapeLog, Source
from src.scraper.source_stats import SourceStatsRow, load_source_stats
from src.scraper.source_tiers import tier_for_module

_HEALTH_ICON = {"error": "🔴", "warn": "🟡", "ok": "🟢", "idle": "⚪"}


def _pct(rate: float) -> str:
    return f"{int(rate * 100)}%"


def health_icon(health: str) -> str:
    return _HEALTH_ICON.get(health, "⚪")


def split_telegram_messages(text: str, *, limit: int = 3900) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    chunk: list[str] = []
    size = 0
    for line in text.split("\n"):
        line_len = len(line) + 1
        if size + line_len > limit and chunk:
            parts.append("\n".join(chunk))
            chunk = []
            size = 0
        chunk.append(line)
        size += line_len
    if chunk:
        parts.append("\n".join(chunk))
    return parts


async def _scheduler_ok(session: AsyncSession) -> tuple[bool, str]:
    last = await session.scalar(
        select(ScrapeLog.started_at)
        .order_by(ScrapeLog.started_at.desc())
        .limit(1)
    )
    if not last:
        return False, "no scrape logs"
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    age_h = (datetime.now(timezone.utc) - last).total_seconds() / 3600
    if age_h > 3:
        return False, f"last scrape {age_h:.1f}h ago"
    return True, f"last scrape {age_h:.1f}h ago"


def _sort_sources(
    sources: list[Source], stats: dict[int, SourceStatsRow]
) -> list[Source]:
    order = {"error": 0, "warn": 1, "idle": 2, "ok": 3}

    def key(s: Source) -> tuple:
        st = stats.get(s.id)
        h = st.health if st else "idle"
        er = st.error_rate if st else 0.0
        saved = st.items_saved if st else 0
        return (order.get(h, 9), -er, -saved)

    return sorted(sources, key=key)


async def build_dashboard_text(session: AsyncSession) -> str:
    days = settings.source_stats_days
    stats = await load_source_stats(session, days=days)
    sources = list((await session.scalars(select(Source).order_by(Source.id))).all())
    since_24h = datetime.now(timezone.utc) - timedelta(hours=24)

    saved_24h = await session.scalar(
        select(func.coalesce(func.sum(ScrapeLog.items_new), 0)).where(
            ScrapeLog.started_at >= since_24h
        )
    )
    errors_24h = await session.scalar(
        select(func.count())
        .select_from(ScrapeLog)
        .where(
            ScrapeLog.started_at >= since_24h,
            ScrapeLog.status == "error",
        )
    )
    ai_pending = len(await _matches_needing_ai(session))
    sched_ok, sched_note = await _scheduler_ok(session)
    log_info = app_log_info()

    lines = [
        f"<b>📊 BetIQ Dashboard</b> ({days}d window)",
        f"24h: <b>+{int(saved_24h or 0)}</b> saved | "
        f"<b>{int(errors_24h or 0)}</b> errors | "
        f"AI pending: <b>{ai_pending}</b>",
        f"Scheduler: {'✅' if sched_ok else '⚠️'} {sched_note}",
        f"Log: {log_info['size_human'] if log_info['exists'] else 'missing'}",
        "",
        "<b>Sources</b> (problems first):",
    ]

    for s in _sort_sources(sources, stats):
        st = stats.get(s.id)
        h = st.health if st else "idle"
        flag = "✅" if s.is_active else "⏸"
        tier = tier_for_module(s.scraper_module).value
        if st and st.runs > 0:
            lines.append(
                f"{health_icon(h)} {flag} <b>{s.name}</b> "
                f"<code>{s.scraper_module}</code> [{tier}]\n"
                f"   runs {st.runs} | +{st.items_saved} | "
                f"err {st.errors} ({_pct(st.error_rate)})"
            )
        else:
            lines.append(
                f"{health_icon(h)} {flag} <b>{s.name}</b> "
                f"<code>{s.scraper_module}</code> [{tier}] — no runs"
            )

    return "\n".join(lines)


async def build_digest_text(session: AsyncSession) -> str:
    """Утренняя сводка: короче dashboard."""
    since_24h = datetime.now(timezone.utc) - timedelta(hours=24)
    saved_24h = await session.scalar(
        select(func.coalesce(func.sum(ScrapeLog.items_new), 0)).where(
            ScrapeLog.started_at >= since_24h
        )
    )
    ai_pending = len(await _matches_needing_ai(session))
    stats = await load_source_stats(session, days=1)
    sources = list((await session.scalars(select(Source))).all())

    problems = []
    for s in _sort_sources(sources, stats):
        st = stats.get(s.id)
        if not st or st.health in ("ok", "idle"):
            continue
        problems.append(
            f"{health_icon(st.health)} {s.name}: "
            f"err {st.errors}/{st.runs}, +{st.items_saved}"
        )

    lines = [
        "<b>☀️ Morning digest</b>",
        f"Last 24h: <b>+{int(saved_24h or 0)}</b> predictions saved",
        f"AI queue: <b>{ai_pending}</b> matches",
    ]
    if problems:
        lines.append("\n<b>Attention:</b>")
        lines.extend(problems[:5])
    else:
        lines.append("\n✅ No problematic sources in last 24h")
    return "\n".join(lines)


async def build_logs_text(
    session: AsyncSession,
    *,
    limit: int = 10,
    module: str | None = None,
    errors_only: bool = False,
) -> str:
    limit = min(max(limit, 1), 50)
    q = select(ScrapeLog).order_by(ScrapeLog.started_at.desc())
    if module:
        source = await session.scalar(
            select(Source).where(Source.scraper_module == module)
        )
        if not source:
            return f"Source not found: <code>{module}</code>"
        q = q.where(ScrapeLog.source_id == source.id)
    if errors_only:
        q = q.where(ScrapeLog.status == "error")

    logs = (await session.scalars(q.limit(limit))).all()
    source_map = {
        s.id: s.name for s in (await session.scalars(select(Source))).all()
    }

    title = f"<b>Scrape logs ({len(logs)})</b>"
    if module:
        title += f" — <code>{module}</code>"
    if errors_only:
        title += " [errors]"
    lines = [title]
    for lg in logs:
        name = source_map.get(lg.source_id, "?")
        err = f"\n  {lg.error_msg[:100]}" if lg.error_msg else ""
        ts = lg.started_at.strftime("%m-%d %H:%M") if lg.started_at else "?"
        lines.append(
            f"• {ts} <b>{name}</b> [{lg.status}] "
            f"+{lg.items_new}/{lg.items_found}{err}"
        )
    if not logs:
        lines.append("No logs.")
    return "\n".join(lines)


def build_log_info_text() -> str:
    info = app_log_info()
    lines = [
        "<b>App log</b>",
        f"Path: <code>{info['path']}</code>",
    ]
    if info["exists"]:
        mod = info["modified_at"]
        mod_s = mod.strftime("%Y-%m-%d %H:%M UTC") if mod else "?"
        lines.append(f"Size: <b>{info['size_human']}</b> ({info['size_bytes']:,} B)")
        lines.append(f"Modified: {mod_s}")
    else:
        lines.append("File not found.")
    return "\n".join(lines)


def read_log_tail(*, lines_count: int = 40) -> str:
    lines_count = min(max(lines_count, 5), 80)
    path = resolve_app_log_path()
    if not path.is_file():
        return "<b>Log tail</b>\nFile not found."
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
    except OSError as e:
        return f"<b>Log tail</b>\nRead error: {e}"

    tail = all_lines[-lines_count:]
    body = "".join(tail)
    if len(body) > 3500:
        body = body[-3500:]
        body = "…\n" + body
    safe = html.escape(body)
    return f"<b>Log tail ({len(tail)} lines)</b>\n<pre>{safe}</pre>"
