"""Константы провайдеров и маппинг спортов."""
from __future__ import annotations

PROVIDER_API_FOOTBALL = "api_football"
PROVIDER_THE_ODDS_API = "the_odds_api"

# football-only для API-Football fixtures/stats
API_FOOTBALL_SPORTS = frozenset({"football"})

# Bulk fetch football odds (клубные лиги + сборные / ЧМ)
from src.api_clients.odds_keys import all_football_odds_keys  # noqa: E402

ODDS_SPORT_KEYS_FOOTBALL = all_football_odds_keys()

_ODDS_KEY_PREFIX_SPORT = (
    ("soccer_", "football"),
    ("tennis_", "tennis"),
    ("basketball_", "basketball"),
    ("icehockey_", "hockey"),
    ("mma_", "mma"),
)


def sport_for_odds_key(sport_key: str) -> str:
    for prefix, sport in _ODDS_KEY_PREFIX_SPORT:
        if sport_key.startswith(prefix):
            return sport
    return "unknown"
