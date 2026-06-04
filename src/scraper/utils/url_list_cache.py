"""Кэш списка URL с категорийных страниц — меньше обходов через прокси при частых scrape."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.config import BASE_DIR, settings

log = logging.getLogger("url_list_cache")

CACHE_DIR = BASE_DIR / "data" / "scrape_url_cache"


def _path(source_id: int) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"source_{source_id}.json"


def get(source_id: int) -> Optional[list[str]]:
    ttl = settings.scrape_url_list_cache_ttl_minutes
    if ttl <= 0:
        return None

    path = _path(source_id)
    if not path.exists():
        return None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        log.warning("URL cache read failed source_id=%s: %s", source_id, e)
        return None

    cached_at = payload.get("cached_at")
    urls = payload.get("urls")
    if not cached_at or not isinstance(urls, list):
        return None

    try:
        ts = datetime.fromisoformat(cached_at.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    except ValueError:
        return None

    age_min = (datetime.now(timezone.utc) - ts).total_seconds() / 60
    if age_min > ttl:
        log.debug("URL cache expired source_id=%s (%.0f min)", source_id, age_min)
        return None

    out = [str(u).strip() for u in urls if u]
    log.info(
        "URL cache hit source_id=%s: %s urls (age %.0f min, ttl %s min)",
        source_id,
        len(out),
        age_min,
        ttl,
    )
    return out


def set(source_id: int, urls: list[str]) -> None:
    if settings.scrape_url_list_cache_ttl_minutes <= 0:
        return
    path = _path(source_id)
    payload = {
        "cached_at": datetime.now(timezone.utc).isoformat(),
        "urls": sorted({u.strip() for u in urls if u}),
    }
    try:
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except OSError as e:
        log.warning("URL cache write failed source_id=%s: %s", source_id, e)


def invalidate(source_id: int) -> None:
    path = _path(source_id)
    try:
        path.unlink(missing_ok=True)
    except OSError as e:
        log.warning("URL cache invalidate failed source_id=%s: %s", source_id, e)
