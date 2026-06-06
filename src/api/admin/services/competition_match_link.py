"""Связь matches.competition (текст) ↔ competitions (справочник)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.sql import ColumnElement

from src.db.models import Competition, Match

_FINISHED_STATUSES = frozenset(
    {"FT", "AET", "PEN", "CANC", "ABD", "AWD", "WO", "PST"}
)


def upcoming_match_date_clause(
    since: datetime, until: datetime
) -> ColumnElement[bool]:
    return and_(
        Match.match_date.isnot(None),
        Match.match_date >= since,
        Match.match_date <= until,
        or_(
            Match.status.is_(None),
            Match.status.notin_(list(_FINISHED_STATUSES)),
        ),
    )


def match_links_competition() -> ColumnElement[bool]:
    """Матч относится к лиге: по competition_id или по тексту competition."""
    league_name = func.lower(func.trim(Competition.name))
    match_comp = func.lower(func.trim(Match.competition))
    return or_(
        Match.competition_id == Competition.id,
        and_(
            Match.competition.isnot(None),
            Match.competition != "",
            match_comp == league_name,
        ),
        and_(
            Match.competition.isnot(None),
            Match.competition != "",
            league_name.like(func.concat("%", match_comp, "%")),
        ),
        and_(
            Match.competition.isnot(None),
            Match.competition != "",
            match_comp.like(func.concat("%", league_name, "%")),
        ),
    )


def upcoming_match_count_scalar(since: datetime, until: datetime):
    return (
        select(func.count(Match.id))
        .where(
            upcoming_match_date_clause(since, until),
            match_links_competition(),
        )
        .correlate(Competition)
        .scalar_subquery()
    )


def competition_search_clause(q: str, since: datetime, until: datetime) -> ColumnElement[bool]:
    like = f"%{q.strip()}%"
    return or_(
        Competition.name.ilike(like),
        Competition.country.ilike(like),
        Competition.country_code.ilike(like),
        select(1)
        .select_from(Match)
        .where(
            upcoming_match_date_clause(since, until),
            match_links_competition(),
            Match.competition.ilike(like),
        )
        .exists(),
    )
