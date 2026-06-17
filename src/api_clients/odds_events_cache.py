"""TTL-кеш GET /sports/{key}/events для linker (экономия кредитов)."""
from __future__ import annotations

from datetime import datetime, timezone

from src.api_clients.the_odds_api import TheOddsApiClient
from src.api_clients.the_odds_api_quota import is_quota_suspended
from src.config import settings

_cache: dict[str, tuple[datetime, list[dict]]] = {}


def clear_events_cache() -> None:
    _cache.clear()


async def get_events_cached(
    client: TheOddsApiClient, sport_key: str
) -> list[dict]:
    if is_quota_suspended():
        entry = _cache.get(sport_key)
        return entry[1] if entry else []

    ttl_sec = max(0, settings.odds_link_events_cache_minutes) * 60
    now = datetime.now(timezone.utc)
    if ttl_sec > 0:
        entry = _cache.get(sport_key)
        if entry and (now - entry[0]).total_seconds() < ttl_sec:
            return entry[1]

    events = await client.get_events(sport_key)
    if ttl_sec > 0:
        _cache[sport_key] = (now, events)
    return events
