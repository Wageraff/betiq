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
            await self._log_quota_headers(resp)
            data = resp.json()
        errors = data.get("errors") or {}
        if errors:
            log.warning("API-Football errors: %s", errors)
        return data.get("response") or []

    @staticmethod
    async def _log_quota_headers(resp: httpx.Response) -> None:
        from src.api_clients.quota_log import save_quota_snapshot

        def _int(h: str) -> int | None:
            try:
                return int(resp.headers.get(h, ""))
            except ValueError:
                return None

        limit = _int("x-ratelimit-requests-limit")
        remaining = _int("x-ratelimit-requests-remaining")
        if remaining is not None:
            used = (limit - remaining) if limit is not None else None
            await save_quota_snapshot("api_football", remaining, used)

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
            # API-Football требует season при фильтре по team.
            if season is None and date:
                season = int(str(date)[:4])
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

    async def get_fixture_odds(self, fixture_id: str | int) -> list[dict]:
        return await self._get("/odds", {"fixture": fixture_id})

    async def get_fixture_injuries(self, fixture_id: str | int) -> list[dict]:
        return await self._get("/injuries", {"fixture": fixture_id})

    async def get_fixture_predictions(self, fixture_id: str | int) -> list[dict]:
        return await self._get("/predictions", {"fixture": fixture_id})

    async def get_headtohead(
        self, team1_id: str | int, team2_id: str | int, *, last: int = 10
    ) -> list[dict]:
        return await self._get(
            "/fixtures/headtohead", {"h2h": f"{team1_id}-{team2_id}", "last": last}
        )

    async def get_account_status(self) -> dict[str, Any]:
        """Лимиты аккаунта: GET /status (не расходует лимит fixtures)."""
        if not self.enabled:
            return {}
        headers = {
            "x-apisports-key": self.api_key,
            "x-rapidapi-key": self.api_key,
        }
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{BASE_URL}/status", headers=headers)
            resp.raise_for_status()
            data = resp.json()
        req = (data.get("response") or {}).get("requests") or {}
        limit_day = req.get("limit_day")
        current = req.get("current")
        if limit_day is not None and current is not None:
            from src.api_clients.quota_log import save_quota_snapshot

            await save_quota_snapshot(
                "api_football",
                int(limit_day) - int(current),
                int(current),
            )
        return data.get("response") or {}
