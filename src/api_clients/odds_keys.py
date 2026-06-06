"""Подбор sport_key The Odds API под матч (лиги vs сборные / ЧМ)."""
from __future__ import annotations

import re

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Match, Team
from src.scraper.utils.team_catalog import COUNTRY_KEYS
from src.scraper.utils.team_names import resolve_team_key

ODDS_KEYS_CLUB_LEAGUES: list[str] = [
    "soccer_epl",
    "soccer_spain_la_liga",
    "soccer_germany_bundesliga",
    "soccer_italy_serie_a",
    "soccer_france_ligue_one",
    "soccer_uefa_champs_league",
    "soccer_uefa_europa_league",
]

# Квалификации africa/asia/oceania/concacaf и copa_america — только в сезон;
# 404 вне сезона обрабатывается в TheOddsApiClient.
ODDS_KEYS_INTERNATIONAL: list[str] = [
    "soccer_fifa_world_cup",
    "soccer_fifa_world_cup_qualifiers_europe",
    "soccer_fifa_world_cup_qualifiers_south_america",
    "soccer_uefa_nations_league",
    "soccer_uefa_euro_qualification",
]

_COMPETITION_PATTERNS: list[tuple[re.Pattern[str], list[str]]] = [
    (
        re.compile(
            r"чм|world\s*cup|fifa|campionatului\s*mondial|mondial",
            re.I,
        ),
        ODDS_KEYS_INTERNATIONAL,
    ),
    (
        re.compile(r"amicale|friendly|товарищ|amic|nations\s*league", re.I),
        ODDS_KEYS_INTERNATIONAL,
    ),
    (
        re.compile(
            r"liga|la\s*liga|primera|serie\s*a|bundesliga|ligue|epl|premier|champions",
            re.I,
        ),
        ODDS_KEYS_CLUB_LEAGUES,
    ),
]


def _is_country_key(key: str) -> bool:
    return resolve_team_key(key) in COUNTRY_KEYS


async def _team_is_national(session: AsyncSession, team_id: int | None) -> bool:
    if not team_id:
        return False
    team = await session.get(Team, team_id)
    if not team:
        return False
    return _is_country_key(team.normalized_key)


async def odds_sport_keys_for_match(session: AsyncSession, match: Match) -> list[str]:
    """Какие sport_key опросить для линковки / odds конкретного матча."""
    sport = match.sport or ""
    if sport != "football":
        from src.api_clients.constants import SPORT_TO_ODDS_KEY

        key = SPORT_TO_ODDS_KEY.get(sport)
        return [key] if key else []

    keys: list[str] = []
    comp = match.competition or ""
    for pattern, sport_keys in _COMPETITION_PATTERNS:
        if pattern.search(comp):
            keys.extend(sport_keys)

    home_nat = await _team_is_national(session, match.team_home_id)
    away_nat = await _team_is_national(session, match.team_away_id)
    if home_nat and away_nat:
        keys.extend(ODDS_KEYS_INTERNATIONAL)
    elif not home_nat or not away_nat:
        keys.extend(ODDS_KEYS_CLUB_LEAGUES)

    if not keys:
        keys = ODDS_KEYS_CLUB_LEAGUES + ODDS_KEYS_INTERNATIONAL

    seen: set[str] = set()
    out: list[str] = []
    for key in keys:
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out


def all_football_odds_keys() -> list[str]:
    """Все football sport_key для bulk-опроса odds."""
    seen: set[str] = set()
    out: list[str] = []
    for key in ODDS_KEYS_CLUB_LEAGUES + ODDS_KEYS_INTERNATIONAL:
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out
