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
            if resp.status_code == 404:
                # Лига вне сезона или sport_key неактивен — не ошибка.
                log.debug("The Odds API 404 (inactive): %s", path)
                return []
            if resp.status_code == 422:
                log.warning("The Odds API invalid params: %s %s", path, resp.text[:200])
                return []
            resp.raise_for_status()
            await self._log_quota_headers(resp)
            data = resp.json()
        if isinstance(data, list):
            return data
        log.warning("The Odds API unexpected response: %s", type(data))
        return []

    @staticmethod
    async def _log_quota_headers(resp: httpx.Response) -> None:
        from src.api_clients.quota_log import save_quota_snapshot

        def _int(h: str) -> int | None:
            try:
                return int(resp.headers.get(h, ""))
            except ValueError:
                return None

        remaining = _int("x-requests-remaining")
        used = _int("x-requests-used")
        if remaining is not None or used is not None:
            await save_quota_snapshot("the_odds_api", remaining, used)

    async def _get_object_with_status(
        self, path: str, params: dict[str, Any] | None = None
    ) -> tuple[dict | None, int | None]:
        if not self.enabled:
            return None, None
        p = dict(params or {})
        p["apiKey"] = self.api_key
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{BASE_URL}{path}", params=p)
            if resp.status_code in (404, 422):
                log.debug("The Odds API %s: %s", resp.status_code, path)
                return None, resp.status_code
            resp.raise_for_status()
            await self._log_quota_headers(resp)
            data = resp.json()
        payload = data if isinstance(data, dict) else None
        return payload, resp.status_code

    async def _get_object(
        self, path: str, params: dict[str, Any] | None = None
    ) -> dict | None:
        data, _status = await self._get_object_with_status(path, params)
        return data

    async def get_events(self, sport_key: str) -> list[dict]:
        return await self._get(f"/sports/{sport_key}/events")

    async def get_odds(
        self,
        sport_key: str,
        *,
        regions: str = "eu",
        markets: str | None = None,
    ) -> list[dict]:
        mkt = markets or settings.the_odds_api_markets
        return await self._get(
            f"/sports/{sport_key}/odds",
            {"regions": regions, "markets": mkt, "oddsFormat": "decimal"},
        )

    async def get_event_odds(
        self,
        sport_key: str,
        event_id: str,
        *,
        regions: str = "eu",
        markets: str | None = None,
    ) -> dict | None:
        """Расширенные рынки — только per-event endpoint (btts, alternate_*, …)."""
        mkt = markets or settings.the_odds_api_event_markets
        if not mkt.strip():
            return None
        return await self._get_object(
            f"/sports/{sport_key}/events/{event_id}/odds",
            {"regions": regions, "markets": mkt, "oddsFormat": "decimal"},
        )

    async def get_event_odds_with_status(
        self,
        sport_key: str,
        event_id: str,
        *,
        regions: str = "eu",
        markets: str | None = None,
    ) -> tuple[dict | None, int | None]:
        """Per-event odds + HTTP status (404 = устаревший event_id)."""
        mkt = markets or settings.the_odds_api_event_markets
        if not mkt.strip():
            return None, None
        return await self._get_object_with_status(
            f"/sports/{sport_key}/events/{event_id}/odds",
            {"regions": regions, "markets": mkt, "oddsFormat": "decimal"},
        )

    async def get_quota(self) -> dict[str, int | None]:
        """Остаток кредитов из заголовков (GET /sports не считается в квоту)."""
        if not self.enabled:
            return {"remaining": None, "used": None}
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{BASE_URL}/sports",
                params={"apiKey": self.api_key},
            )
            resp.raise_for_status()
        def _int(h: str) -> int | None:
            try:
                return int(resp.headers.get(h, ""))
            except ValueError:
                return None
        return {
            "remaining": _int("x-requests-remaining"),
            "used": _int("x-requests-used"),
        }
