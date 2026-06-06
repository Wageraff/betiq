"""Подбор sport_key The Odds API под матч (все виды спорта)."""
from __future__ import annotations

import re

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Match, Team
from src.scraper.utils.team_catalog import COUNTRY_KEYS
from src.scraper.utils.team_names import resolve_team_key

# --- подписи для админки ---
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
    "basketball_nba": "NBA",
    "basketball_wnba": "WNBA",
    "basketball_euroleague": "Euroleague",
    "basketball_ncaab": "NCAA Basketball",
    "icehockey_nhl": "NHL",
    "icehockey_khl": "KHL",
    "icehockey_sweden_hockey_league": "SHL (Sweden)",
    "mma_mixed_martial_arts": "MMA / UFC",
    "tennis_atp_french_open": "Tennis ATP — French Open",
    "tennis_wta_french_open": "Tennis WTA — French Open",
    "tennis_atp_wimbledon": "Tennis ATP — Wimbledon",
    "tennis_wta_wimbledon": "Tennis WTA — Wimbledon",
    "tennis_atp_us_open": "Tennis ATP — US Open",
    "tennis_wta_us_open": "Tennis WTA — US Open",
    "tennis_atp_australian_open": "Tennis ATP — Australian Open",
    "tennis_wta_australian_open": "Tennis WTA — Australian Open",
    "tennis_atp_indian_wells": "Tennis ATP — Indian Wells",
    "tennis_wta_indian_wells": "Tennis WTA — Indian Wells",
    "tennis_atp_miami_open": "Tennis ATP — Miami",
    "tennis_wta_miami_open": "Tennis WTA — Miami",
    "tennis_atp_monte_carlo": "Tennis ATP — Monte Carlo",
    "tennis_atp_madrid_open": "Tennis ATP — Madrid",
    "tennis_atp_italian_open": "Tennis ATP — Rome",
    "tennis_atp_cincinnati_open": "Tennis ATP — Cincinnati",
    "tennis_atp_shanghai_masters": "Tennis ATP — Shanghai",
    "tennis_atp_paris_masters": "Tennis ATP — Paris Masters",
}

_WTA_RE = re.compile(r"\bwta\b|women|женск|ladies", re.I)
_ATP_RE = re.compile(r"\batp\b|men|мужск", re.I)

_FOOTBALL_RULES: list[tuple[re.Pattern[str], str]] = [
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

# (pattern, atp_key, wta_key) — для тенниса; None = не использовать этот тур
_TENNIS_TOURNAMENT_RULES: list[tuple[re.Pattern[str], str | None, str | None]] = [
    (re.compile(r"roland\s*garros|french\s*open|французск|roland-garros", re.I), "tennis_atp_french_open", "tennis_wta_french_open"),
    (re.compile(r"wimbledon|уимблдон", re.I), "tennis_atp_wimbledon", "tennis_wta_wimbledon"),
    (re.compile(r"us\s*open|u\.?\s*s\.?\s*open|открыт.*сша", re.I), "tennis_atp_us_open", "tennis_wta_us_open"),
    (re.compile(r"australian\s*open|открыт.*австрал", re.I), "tennis_atp_australian_open", "tennis_wta_australian_open"),
    (re.compile(r"indian\s*wells|indian-wells", re.I), "tennis_atp_indian_wells", "tennis_wta_indian_wells"),
    (re.compile(r"miami\s*open|miami-open", re.I), "tennis_atp_miami_open", "tennis_wta_miami_open"),
    (re.compile(r"monte\s*carlo|monte-carlo|монте", re.I), "tennis_atp_monte_carlo", None),
    (re.compile(r"madrid\s*open|mutua", re.I), "tennis_atp_madrid_open", None),
    (re.compile(r"italian\s*open|internazionali|rome|roma.*masters", re.I), "tennis_atp_italian_open", None),
    (re.compile(r"cincinnati", re.I), "tennis_atp_cincinnati_open", None),
    (re.compile(r"shanghai", re.I), "tennis_atp_shanghai_masters", None),
    (re.compile(r"paris\s*masters|rolex\s*paris", re.I), "tennis_atp_paris_masters", None),
]

_OTHER_SPORT_RULES: dict[str, list[tuple[re.Pattern[str], str]]] = {
    "basketball": [
        (re.compile(r"\bnba\b|энба", re.I), "basketball_nba"),
        (re.compile(r"wnba", re.I), "basketball_wnba"),
        (re.compile(r"euroleague|евролиг|euro\s*league", re.I), "basketball_euroleague"),
        (re.compile(r"ncaa|college\s*basket", re.I), "basketball_ncaab"),
        (re.compile(r"vtb|втб", re.I), "basketball_euroleague"),
    ],
    "hockey": [
        (re.compile(r"\bnhl\b|нхл", re.I), "icehockey_nhl"),
        (re.compile(r"\bkhl\b|кхл", re.I), "icehockey_khl"),
        (re.compile(r"\bshl\b|sweden|швец", re.I), "icehockey_sweden_hockey_league"),
    ],
    "mma": [
        (re.compile(r"ufc|mma|bellator|pfl", re.I), "mma_mixed_martial_arts"),
    ],
}

# Fallback, если competition пустой или не распознан (только для явного sport)
SPORT_DEFAULT_ODDS_KEYS: dict[str, list[str]] = {
    "basketball": ["basketball_nba"],
    "hockey": ["icehockey_nhl"],
    "mma": ["mma_mixed_martial_arts"],
    "tennis": [],
}

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

SPORTS_WITH_ODDS_API = frozenset(
    {"football", "tennis", "basketball", "hockey", "mma"}
)


def _dedupe(keys: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for key in keys:
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out


def _tennis_keys_from_competition(comp: str) -> list[str]:
    comp = comp or ""
    for pattern, atp_key, wta_key in _TENNIS_TOURNAMENT_RULES:
        if not pattern.search(comp):
            continue
        keys: list[str] = []
        if _WTA_RE.search(comp):
            if wta_key:
                keys.append(wta_key)
            return keys
        if _ATP_RE.search(comp):
            if atp_key:
                keys.append(atp_key)
            return keys
        if atp_key:
            keys.append(atp_key)
        if wta_key:
            keys.append(wta_key)
        return _dedupe(keys)
    return []


def _keys_from_rules(sport: str, comp: str) -> list[str]:
    rules = _OTHER_SPORT_RULES.get(sport, [])
    for pattern, key in rules:
        if pattern.search(comp):
            return [key]
    return []


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
    sport = (match.sport or "").strip().lower()
    comp = match.competition or ""

    if sport == "football":
        for pattern, key in _FOOTBALL_RULES:
            if pattern.search(comp):
                return [key]
        home_nat = await _team_is_national(session, match.team_home_id)
        away_nat = await _team_is_national(session, match.team_away_id)
        if home_nat and away_nat:
            if _INTERNATIONAL_COMP_RE.search(comp):
                return list(ODDS_KEYS_INTERNATIONAL)
            return ["soccer_fifa_world_cup", "soccer_uefa_nations_league"]
        return []

    if sport == "tennis":
        keys = _tennis_keys_from_competition(comp)
        if keys:
            return keys
        if _WTA_RE.search(comp):
            return ["tennis_wta_french_open"]
        if _ATP_RE.search(comp):
            return ["tennis_atp_french_open"]
        return SPORT_DEFAULT_ODDS_KEYS.get("tennis", [])

    if sport in _OTHER_SPORT_RULES:
        keys = _keys_from_rules(sport, comp)
        if keys:
            return keys
        if sport == "mma" or re.search(r"ufc|mma", comp, re.I):
            return ["mma_mixed_martial_arts"]
        return SPORT_DEFAULT_ODDS_KEYS.get(sport, [])

    return []


def all_football_odds_keys() -> list[str]:
    return _dedupe(ODDS_KEYS_CLUB_LEAGUES + ODDS_KEYS_INTERNATIONAL)


def all_non_football_odds_keys() -> list[str]:
    keys: list[str] = []
    for defaults in SPORT_DEFAULT_ODDS_KEYS.values():
        keys.extend(defaults)
    for rules in _OTHER_SPORT_RULES.values():
        for _, key in rules:
            keys.append(key)
    for _, atp, wta in _TENNIS_TOURNAMENT_RULES:
        if atp:
            keys.append(atp)
        if wta:
            keys.append(wta)
    return _dedupe(keys)


def all_odds_keys_all_sports() -> list[str]:
    return _dedupe(all_football_odds_keys() + all_non_football_odds_keys())
