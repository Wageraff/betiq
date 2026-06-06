"""The Odds API v4 client (https://the-odds-api.com/liveapi/guides/v4/)."""
from __future__ import annotations

import logging
from typing import Any

import httpx

from src.config import settings

log = logging.getLogger("the_odds_api")

BASE_URL = "https://api.the-odds-api.com/v4"


class TheOddsApiClient:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or settings.the_odds_api_key

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> list[dict]:
        if not self.enabled:
            return []
        p = dict(params or {})
        p["apiKey"] = self.api_key
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{BASE_URL}{path}", params=p)
            resp.raise_for_status()
            data = resp.json()
        if isinstance(data, list):
            return data
        log.warning("The Odds API unexpected response: %s", type(data))
        return []

    async def get_events(self, sport_key: str) -> list[dict]:
        return await self._get(f"/sports/{sport_key}/events")

    async def get_odds(
        self,
        sport_key: str,
        *,
        regions: str = "eu",
        markets: str = "h2h,spreads,totals",
    ) -> list[dict]:
        return await self._get(
            f"/sports/{sport_key}/odds",
            {"regions": regions, "markets": markets, "oddsFormat": "decimal"},
        )
