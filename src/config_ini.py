"""Чтение и запись config.ini (секция [api_sync] и др.)."""
from __future__ import annotations

import configparser
from pathlib import Path
from typing import Any

from src.config import CONFIG_PATH

# Ключи [api_sync], редактируемые из админки → имя поля в API
API_SYNC_INI_KEYS: dict[str, str] = {
    "enabled": "enabled",
    "link_batch_size": "link_batch_size",
    "odds_sync_mode": "odds_sync_mode",
    "odds_upcoming_days_ahead": "odds_upcoming_days_ahead",
    "odds_skip_finished_hours": "odds_skip_finished_hours",
    "odds_min_interval_minutes": "odds_min_interval_minutes",
    "odds_markets": "odds_markets",
    "odds_event_markets": "odds_event_markets",
    "odds_event_batch_size": "odds_event_batch_size",
    "api_football_odds_enabled": "api_football_odds_enabled",
    "api_football_odds_days_ahead": "api_football_odds_days_ahead",
    "api_football_odds_batch_size": "api_football_odds_batch_size",
    "api_football_odds_markets": "api_football_odds_markets",
    "api_fixture_refresh_limit": "api_fixture_refresh_limit",
    "admin_match_odds_limit": "admin_match_odds_limit",
    "api_quota_alert_threshold": "api_quota_alert_threshold",
}


def _read_parser(path: Path | None = None) -> configparser.ConfigParser:
    cp = configparser.ConfigParser(interpolation=None)
    target = path or CONFIG_PATH
    if target.exists():
        cp.read(target, encoding="utf-8")
    return cp


def update_api_sync_section(updates: dict[str, Any], *, path: Path | None = None) -> list[str]:
    """Записать ключи в [api_sync]. Возвращает список изменённых ключей."""
    target = path or CONFIG_PATH
    cp = _read_parser(target)
    if not cp.has_section("api_sync"):
        cp.add_section("api_sync")

    changed: list[str] = []
    for ini_key, value in updates.items():
        if ini_key not in API_SYNC_INI_KEYS:
            continue
        new_val = _serialize_ini_value(value)
        old_val = cp.get("api_sync", ini_key, fallback=None)
        if old_val != new_val:
            cp.set("api_sync", ini_key, new_val)
            changed.append(ini_key)

    if changed:
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            cp.write(f)
    return changed


def _serialize_ini_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value).strip()
