"""Константы провайдеров и маппинг спортов."""
from __future__ import annotations

PROVIDER_API_FOOTBALL = "api_football"
PROVIDER_THE_ODDS_API = "the_odds_api"

# football-only для API-Football fixtures/stats
API_FOOTBALL_SPORTS = frozenset({"football"})

# The Odds API sport_key по нашему sport (расширяется по мере необходимости)
SPORT_TO_ODDS_KEY: dict[str, str] = {
    "football": "soccer_epl",
    "tennis": "tennis_atp_french_open",
    "basketball": "basketball_nba",
    "hockey": "icehockey_nhl",
    "mma": "mma_mixed_martial_arts",
}

# Обратный маппинг для bulk fetch по лигам (football)
ODDS_SPORT_KEYS_FOOTBALL = [
    "soccer_epl",
    "soccer_spain_la_liga",
    "soccer_germany_bundesliga",
    "soccer_italy_serie_a",
    "soccer_france_ligue_one",
    "soccer_uefa_champs_league",
]


def sport_for_odds_key(sport_key: str) -> str:
    if sport_key.startswith("soccer_"):
        return "football"
    for sport, key in SPORT_TO_ODDS_KEY.items():
        if key == sport_key:
            return sport
    return "unknown"
