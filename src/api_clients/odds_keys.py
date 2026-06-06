"""Подбор sport_key The Odds API под матч (лиги vs сборные / ЧМ)."""
from __future__ import annotations

import re

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Match, Team
from src.scraper.utils.team_catalog import COUNTRY_KEYS
from src.scraper.utils.team_names import resolve_team_key

# Человекочитаемые названия для админки
ODDS_KEY_LABELS: dict[str, str] = {
    "soccer_epl": "Premier League (England)",
    "soccer_spain_la_liga": "La Liga",
    "soccer_germany_bundesliga": "Bundesliga",
    "soccer_italy_serie_a": "Serie A",
    "soccer_france_ligue_one": "Ligue 1",
    "soccer_uefa_champs_league": "UEFA Champions League",
    "soccer_uefa_europa_league": "UEFA Europa League",
    "soccer_russia_premier_league": "Premier League (Russia / РПЛ)",
    "soccer_romania_liga_1": "Liga I (Romania)",
    "soccer_turkey_super_league": "Süper Lig (Turkey)",
    "soccer_netherlands_eredivisie": "Eredivisie",
    "soccer_portugal_primeira_liga": "Primeira Liga",
    "soccer_fifa_world_cup": "FIFA World Cup",
    "soccer_fifa_world_cup_qualifiers_europe": "WC Qualifiers (Europe)",
    "soccer_fifa_world_cup_qualifiers_south_america": "WC Qualifiers (South America)",
    "soccer_uefa_nations_league": "UEFA Nations League",
    "soccer_uefa_euro_qualification": "Euro Qualification",
}

# Точное сопоставление competition → один sport_key (проверяется первым)
_SPECIFIC_LEAGUE_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"чм|world\s*cup|fifa\s*world|campionatului\s*mondial|mondial", re.I), "soccer_fifa_world_cup"),
    (re.compile(r"champions\s*league|liga\s*campionilor|лч\b|uefa\s*champions", re.I), "soccer_uefa_champs_league"),
    (re.compile(r"europa\s*league|liga\s*europa|ле\b|uefa\s*europa", re.I), "soccer_uefa_europa_league"),
    (re.compile(r"\bepl\b|premier\s*league(?!.*russia)|англи", re.I), "soccer_epl"),
    (re.compile(r"la\s*liga|primera\s*divisi[oó]n|испан", re.I), "soccer_spain_la_liga"),
    (re.compile(r"bundesliga|бундес", re.I), "soccer_germany_bundesliga"),
    (re.compile(r"serie\s*a|серия\s*а", re.I), "soccer_italy_serie_a"),
    (re.compile(r"ligue\s*1|лига\s*1.*фран", re.I), "soccer_france_ligue_one"),
    (re.compile(r"рпл|rpl|premier\s*league.*russia|russia.*premier|российск", re.I), "soccer_russia_premier_league"),
    (re.compile(r"liga\s*i\b|liga\s*1.*rom|superliga.*rom|romania|românia|румын|romaniei", re.I), "soccer_romania_liga_1"),
    (re.compile(r"s[uü]per\s*lig|turkey|турц", re.I), "soccer_turkey_super_league"),
    (re.compile(r"eredivisie|нидерланд", re.I), "soccer_netherlands_eredivisie"),
    (re.compile(r"primeira\s*liga|portugal", re.I), "soccer_portugal_primeira_liga"),
    (re.compile(r"nations\s*league|лига\s*наций", re.I), "soccer_uefa_nations_league"),
    (re.compile(r"euro\s*qual|отбор.*евро", re.I), "soccer_uefa_euro_qualification"),
    (re.compile(r"qualif.*world|отбор.*чм", re.I), "soccer_fifa_world_cup_qualifiers_europe"),
]

ODDS_KEYS_INTERNATIONAL: list[str] = [
    "soccer_fifa_world_cup",
    "soccer_fifa_world_cup_qualifiers_europe",
    "soccer_fifa_world_cup_qualifiers_south_america",
    "soccer_uefa_nations_league",
    "soccer_uefa_euro_qualification",
]

ODDS_KEYS_CLUB_LEAGUES: list[str] = [
    "soccer_epl",
    "soccer_spain_la_liga",
    "soccer_germany_bundesliga",
    "soccer_italy_serie_a",
    "soccer_france_ligue_one",
    "soccer_uefa_champs_league",
    "soccer_uefa_europa_league",
    "soccer_russia_premier_league",
    "soccer_romania_liga_1",
    "soccer_turkey_super_league",
    "soccer_netherlands_eredivisie",
    "soccer_portugal_primeira_liga",
]

_INTERNATIONAL_COMP_RE = re.compile(
    r"amicale|friendly|товарищ|amic|world\s*cup|чм|fifa|nations\s*league|qualif",
    re.I,
)


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

    comp = match.competition or ""
    for pattern, key in _SPECIFIC_LEAGUE_RULES:
        if pattern.search(comp):
            return [key]

    home_nat = await _team_is_national(session, match.team_home_id)
    away_nat = await _team_is_national(session, match.team_away_id)
    if home_nat and away_nat:
        if _INTERNATIONAL_COMP_RE.search(comp):
            return list(ODDS_KEYS_INTERNATIONAL)
        return ["soccer_fifa_world_cup", "soccer_uefa_nations_league"]

    return []


def all_football_odds_keys() -> list[str]:
    """Все football sport_key (режим all_leagues)."""
    seen: set[str] = set()
    out: list[str] = []
    for key in ODDS_KEYS_CLUB_LEAGUES + ODDS_KEYS_INTERNATIONAL:
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out
