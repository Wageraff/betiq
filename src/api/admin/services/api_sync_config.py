"""Настройки [api_sync] в config.ini — чтение и запись из админки."""
from __future__ import annotations

from typing import Any

from src.config import CONFIG_PATH, reload_from_config_ini, settings
from src.config_ini import API_SYNC_INI_KEYS, update_api_sync_section

_ODDS_SYNC_MODES = frozenset({"db_matches", "all_leagues"})


def api_sync_config_out() -> dict[str, Any]:
    return {
        "config_path": str(CONFIG_PATH),
        "enabled": settings.api_sync_enabled,
        "link_batch_size": settings.api_link_batch_size,
        "fixture_refresh_limit": settings.api_fixture_refresh_limit,
        "odds_sync_mode": settings.odds_sync_mode,
        "odds_upcoming_days_ahead": settings.odds_upcoming_days_ahead,
        "odds_skip_finished_hours": settings.odds_skip_finished_hours,
        "odds_min_interval_minutes": settings.odds_min_interval_minutes,
        "api_quota_alert_threshold": settings.api_quota_alert_threshold,
        "admin_match_odds_limit": settings.admin_match_odds_limit,
        "the_odds_api": {
            "odds_markets": settings.the_odds_api_markets,
            "odds_event_markets": settings.the_odds_api_event_markets,
            "odds_event_batch_size": settings.the_odds_api_event_batch_size,
        },
        "api_football": {
            "odds_enabled": settings.api_football_odds_enabled,
            "odds_days_ahead": settings.api_football_odds_days_ahead,
            "odds_batch_size": settings.api_football_odds_batch_size,
            "odds_markets": settings.api_football_odds_markets,
        },
    }


def _normalize_updates(body: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}

    if "enabled" in body and body["enabled"] is not None:
        out["enabled"] = bool(body["enabled"])

    for key in (
        "link_batch_size",
        "fixture_refresh_limit",
        "odds_upcoming_days_ahead",
        "odds_skip_finished_hours",
        "odds_min_interval_minutes",
        "odds_event_batch_size",
        "api_football_odds_days_ahead",
        "api_football_odds_batch_size",
        "admin_match_odds_limit",
        "api_quota_alert_threshold",
    ):
        if key in body and body[key] is not None:
            val = int(body[key])
            if val < 0:
                raise ValueError(f"{key} must be >= 0")
            out[key] = val

    if "odds_sync_mode" in body and body["odds_sync_mode"] is not None:
        mode = str(body["odds_sync_mode"]).strip()
        if mode not in _ODDS_SYNC_MODES:
            raise ValueError(f"odds_sync_mode must be one of: {sorted(_ODDS_SYNC_MODES)}")
        out["odds_sync_mode"] = mode

    for key in ("odds_markets", "odds_event_markets", "api_football_odds_markets"):
        if key in body and body[key] is not None:
            out[key] = str(body[key]).strip()

    if "api_football_odds_enabled" in body and body["api_football_odds_enabled"] is not None:
        out["api_football_odds_enabled"] = bool(body["api_football_odds_enabled"])

    toa = body.get("the_odds_api") or {}
    if isinstance(toa, dict):
        if toa.get("odds_markets") is not None:
            out["odds_markets"] = str(toa["odds_markets"]).strip()
        if toa.get("odds_event_markets") is not None:
            out["odds_event_markets"] = str(toa["odds_event_markets"]).strip()
        if toa.get("odds_event_batch_size") is not None:
            out["odds_event_batch_size"] = int(toa["odds_event_batch_size"])

    af = body.get("api_football") or {}
    if isinstance(af, dict):
        if af.get("odds_enabled") is not None:
            out["api_football_odds_enabled"] = bool(af["odds_enabled"])
        if af.get("odds_days_ahead") is not None:
            out["api_football_odds_days_ahead"] = int(af["odds_days_ahead"])
        if af.get("odds_batch_size") is not None:
            out["api_football_odds_batch_size"] = int(af["odds_batch_size"])
        if af.get("odds_markets") is not None:
            out["api_football_odds_markets"] = str(af["odds_markets"]).strip()

    allowed_ini = set(API_SYNC_INI_KEYS.keys())
    for key in out:
        if key not in allowed_ini:
            raise ValueError(f"Cannot write config key: {key}")

    return out


def save_api_sync_config(body: dict[str, Any]) -> dict[str, Any]:
    updates = _normalize_updates(body)
    if not updates:
        return {"changed": [], "config": api_sync_config_out()}
    changed = update_api_sync_section(updates)
    reload_from_config_ini()
    return {"changed": changed, "config": api_sync_config_out()}
