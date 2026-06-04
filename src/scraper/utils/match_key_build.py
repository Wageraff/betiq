"""Построение match_key / slug без зависимости от БД."""
from __future__ import annotations

from datetime import date

from src.scraper.utils.team_names import canonical_team_key


def build_match_key(team_home: str, team_away: str, match_date: date) -> str:
    home = canonical_team_key(team_home)
    away = canonical_team_key(team_away)
    return f"{home}:{away}:{match_date.isoformat()}"


def build_slug(team_home: str, team_away: str, match_date: date) -> str:
    home = canonical_team_key(team_home)
    away = canonical_team_key(team_away)
    return f"{home}-vs-{away}-{match_date.strftime('%d-%m-%Y')}"
