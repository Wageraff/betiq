"""Агрегаты scrape_logs для админки."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import ScrapeLog


@dataclass(frozen=True)
class SourceStatsRow:
    source_id: int
    runs: int
    items_saved: int
    errors: int
    empty_runs: int
    last_run_at: datetime | None
    last_error_at: datetime | None

    @property
    def error_rate(self) -> float:
        if self.runs == 0:
            return 0.0
        return self.errors / self.runs

    @property
    def save_rate(self) -> float:
        if self.runs == 0:
            return 0.0
        return self.items_saved / self.runs

    @property
    def health(self) -> str:
        """ok | warn | error | idle — для подсветки в UI."""
        if self.runs == 0:
            return "idle"
        if self.error_rate >= 0.3:
            return "error"
        if self.error_rate >= 0.1 or (self.empty_runs / self.runs) >= 0.7:
            return "warn"
        return "ok"


async def load_source_stats(
    session: AsyncSession,
    *,
    days: int = 7,
) -> dict[int, SourceStatsRow]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = await session.execute(
        select(
            ScrapeLog.source_id,
            func.count().label("runs"),
            func.coalesce(func.sum(ScrapeLog.items_new), 0).label("items_saved"),
            func.coalesce(
                func.sum(case((ScrapeLog.status == "error", 1), else_=0)),
                0,
            ).label("errors"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            (ScrapeLog.items_new == 0) & (ScrapeLog.status != "error"),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("empty_runs"),
            func.max(ScrapeLog.started_at).label("last_run_at"),
            func.max(
                case((ScrapeLog.status == "error", ScrapeLog.started_at), else_=None)
            ).label("last_error_at"),
        )
        .where(ScrapeLog.started_at >= since, ScrapeLog.source_id.isnot(None))
        .group_by(ScrapeLog.source_id)
    )
    out: dict[int, SourceStatsRow] = {}
    for row in rows:
        if row.source_id is None:
            continue
        out[row.source_id] = SourceStatsRow(
            source_id=row.source_id,
            runs=int(row.runs or 0),
            items_saved=int(row.items_saved or 0),
            errors=int(row.errors or 0),
            empty_runs=int(row.empty_runs or 0),
            last_run_at=row.last_run_at,
            last_error_at=row.last_error_at,
        )
    return out
