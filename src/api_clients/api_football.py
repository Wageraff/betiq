"""API-Football v3 client (https://www.api-football.com/documentation-v3)."""
from __future__ import annotations

import logging
from typing import Any

import httpx

from src.config import settings

log = logging.getLogger("api_football")

BASE_URL = "https://v3.football.api-sports.io"


class ApiFootballClient:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or settings.api_football_key

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> list[dict]:
        if not self.enabled:
            return []
        headers = {
            "x-apisports-key": self.api_key,
            "x-rapidapi-key": self.api_key,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{BASE_URL}{path}", headers=headers, params=params or {})
            resp.raise_for_status()
            data = resp.json()
        errors = data.get("errors") or {}
        if errors:
            log.warning("API-Football errors: %s", errors)
        return data.get("response") or []

    async def get_leagues(self, *, season: int | None = None) -> list[dict]:
        params: dict[str, Any] = {}
        if season:
            params["season"] = season
        return await self._get("/leagues", params)

    async def get_fixtures(
        self,
        *,
        date: str | None = None,
        team: int | str | None = None,
        fixture: int | str | None = None,
        league: int | str | None = None,
        season: int | None = None,
        last: int | None = None,
    ) -> list[dict]:
        params: dict[str, Any] = {}
        if date:
            params["date"] = date
        if team is not None:
            params["team"] = team
        if fixture is not None:
            params["id"] = fixture
        if league is not None:
            params["league"] = league
        if season is not None:
            params["season"] = season
        if last is not None:
            params["last"] = last
        return await self._get("/fixtures", params)

    async def get_fixture_statistics(self, fixture_id: str | int) -> list[dict]:
        return await self._get("/fixtures/statistics", {"fixture": fixture_id})

    async def get_fixture_lineups(self, fixture_id: str | int) -> list[dict]:
        return await self._get("/fixtures/lineups", {"fixture": fixture_id})
