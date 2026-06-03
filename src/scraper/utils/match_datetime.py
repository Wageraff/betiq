"""
Универсальная модель времени начала матча.

Контракт:
- В БД и в API поле matchDate — момент начала в UTC (ISO 8601 с суффиксом Z / +00:00).
- matchDateTimezone — всегда «UTC» (как записано в API).
- matchDateSourceTimezone — IANA-зона, в которой на сайте-источнике показано время
  (парсер интерпретировал «3 iunie, 21:00» как Europe/Bucharest и перевёл в UTC).

Другие сайты/парсеры: задайте source_timezone в config.ini или передайте source_tz
в to_storage_datetime() / parse_match_datetime().
"""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional, Union
from zoneinfo import ZoneInfo

from src.config import settings

# IANA-имя зоны хранения в БД и в JSON API
MATCH_DATETIME_STORAGE_TZ = "UTC"
STORAGE_TZ = ZoneInfo(MATCH_DATETIME_STORAGE_TZ)

GEO_SOURCE_TZ: dict[str, str] = {
    "RO": "Europe/Bucharest",
    "UK": "Europe/London",
    "DE": "Europe/Berlin",
}


def source_tz_for_geo(geo: Optional[str] = None) -> str:
    if geo and geo.upper() in GEO_SOURCE_TZ:
        return GEO_SOURCE_TZ[geo.upper()]
    return settings.match_datetime_source_tz


def get_source_zoneinfo(geo: Optional[str] = None) -> ZoneInfo:
    return ZoneInfo(source_tz_for_geo(geo))


def to_storage_datetime(
    dt: Optional[datetime],
    *,
    source_tz: Optional[str] = None,
    geo: Optional[str] = None,
) -> Optional[datetime]:
    """
    Привести datetime к aware UTC для записи в matches.match_date.
    Naive datetime считается локальным временем source_tz (не UTC).
    """
    if dt is None:
        return None
    tz = ZoneInfo(source_tz or source_tz_for_geo(geo))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt.astimezone(STORAGE_TZ)


def parse_schema_start_date(
    text: str,
    *,
    source_tz: Optional[str] = None,
    geo: Optional[str] = None,
) -> Optional[datetime]:
    """Legalbet SportsEvent: «2026-06-03 21:00:00» без суффикса — время в source_tz."""
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})\s+(\d{1,2}):(\d{2}):(\d{2})", text.strip())
    if not m:
        return None
    y, mo, d, h, mi, s = (int(x) for x in m.groups())
    tz = get_source_zoneinfo(geo) if not source_tz else ZoneInfo(source_tz)
    local = datetime(y, mo, d, h, mi, s, tzinfo=tz)
    return local.astimezone(STORAGE_TZ)


def default_kickoff_storage(
    d: date,
    *,
    hour: int = 12,
    minute: int = 0,
    source_tz: Optional[str] = None,
    geo: Optional[str] = None,
) -> datetime:
    """Дата без времени на странице → полдень в source_tz → UTC."""
    tz = ZoneInfo(source_tz or source_tz_for_geo(geo))
    local = datetime.combine(d, time(hour, minute), tzinfo=tz)
    return local.astimezone(STORAGE_TZ)


def is_upcoming_match(
    match_date: Optional[datetime],
    *,
    grace_hours: int = 6,
) -> bool:
    if not match_date:
        return True
    kickoff = to_storage_datetime(match_date)
    if not kickoff:
        return True
    cutoff = datetime.now(STORAGE_TZ) - timedelta(hours=grace_hours)
    return kickoff >= cutoff


def api_datetime_meta(geo: Optional[str] = None) -> dict[str, str]:
    """Поля для MatchBriefOut / MatchDetailOut."""
    return {
        "match_date_timezone": MATCH_DATETIME_STORAGE_TZ,
        "match_date_source_timezone": source_tz_for_geo(geo),
    }
