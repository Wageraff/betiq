"""Нормализация дат, коэффициентов и видов спорта."""
from __future__ import annotations

import re
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Optional, Union
from zoneinfo import ZoneInfo

from src.scraper.utils.match_datetime import (
    STORAGE_TZ,
    default_kickoff_storage,
    parse_schema_start_date,
    to_storage_datetime,
)

RU_MONTHS = {
    "января": 1,
    "январь": 1,
    "янв": 1,
    "февраля": 2,
    "февраль": 2,
    "фев": 2,
    "марта": 3,
    "март": 3,
    "мар": 3,
    "апреля": 4,
    "апрель": 4,
    "апр": 4,
    "мая": 5,
    "май": 5,
    "июня": 6,
    "июнь": 6,
    "июн": 6,
    "iyunya": 6,
    "iyune": 6,
    "iyun": 6,
    "июля": 7,
    "июль": 7,
    "июл": 7,
    "августа": 8,
    "август": 8,
    "авг": 8,
    "сентября": 9,
    "сентябрь": 9,
    "сен": 9,
    "октября": 10,
    "октябрь": 10,
    "окт": 10,
    "ноября": 11,
    "ноябрь": 11,
    "ноя": 11,
    "декабря": 12,
    "декабрь": 12,
    "дек": 12,
}

RO_MONTHS = {
    "ianuarie": 1,
    "ian": 1,
    "februarie": 2,
    "feb": 2,
    "martie": 3,
    "mar": 3,
    "aprilie": 4,
    "apr": 4,
    "mai": 5,
    "iunie": 6,
    "iun": 6,
    "iulie": 7,
    "iul": 7,
    "august": 8,
    "aug": 8,
    "septembrie": 9,
    "sep": 9,
    "octombrie": 10,
    "oct": 10,
    "noiembrie": 11,
    "noi": 11,
    "decembrie": 12,
    "dec": 12,
}

def _months_for_geo(geo: Optional[str]) -> dict[str, int]:
    if geo and geo.upper() == "RU":
        merged = dict(RO_MONTHS)
        merged.update(RU_MONTHS)
        return merged
    return RO_MONTHS


SPORT_ALIASES = {
    "fotbal": "football",
    "futbol": "football",
    "футбол": "football",
    "football": "football",
    "soccer": "football",
    "tenis": "tennis",
    "tennis": "tennis",
    "теннис": "tennis",
    "baschet": "basketball",
    "basketbol": "basketball",
    "баскетбол": "basketball",
    "basketball": "basketball",
    "handbal": "handball",
    "handball": "handball",
    "hochei": "hockey",
    "hokkej": "hockey",
    "хоккей": "hockey",
    "hockey": "hockey",
    "volei": "volleyball",
    "volejbol": "volleyball",
    "волейбол": "volleyball",
    "volleyball": "volleyball",
    "mma": "mma",
    "ufc": "mma",
    "formula 1": "motorsport",
    "formula-1": "motorsport",
    "motogp": "motorsport",
}


def normalize_sport(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    key = raw.strip().lower()
    return SPORT_ALIASES.get(key, key.replace(" ", "-") if key else None)


def parse_odds(value: Union[str, float, int, Decimal, None]) -> Optional[Decimal]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    text = str(value).strip().replace(",", ".")
    text = re.sub(r"[^\d.]", "", text)
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _parse_named_month_date(text: str, months: dict[str, int]) -> Optional[date]:
    text = text.strip().lower()
    month_pat = "|".join(sorted(months.keys(), key=len, reverse=True))
    m = re.search(rf"(\d{{1,2}})\s+({month_pat})\s+(\d{{4}})", text, re.I)
    if m:
        day, month_name, year = m.groups()
        month = months.get(month_name.lower())
        if month:
            return date(int(year), month, int(day))

    m = re.search(rf"({month_pat})\s+(\d{{1,2}}),?\s+(\d{{4}})", text, re.I)
    if m:
        month_name, day, year = m.groups()
        month = months.get(month_name.lower())
        if month:
            return date(int(year), month, int(day))

    m = re.search(r"(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})", text)
    if m:
        d, mo, y = m.groups()
        return date(int(y), int(mo), int(d))

    m = re.search(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", text)
    if m:
        y, mo, d = m.groups()
        return date(int(y), int(mo), int(d))
    return None


def _parse_ro_date(text: str, geo: Optional[str] = None) -> Optional[date]:
    return _parse_named_month_date(text, _months_for_geo(geo))


def parse_date(raw: Optional[str], *, geo: Optional[str] = None) -> Optional[datetime]:
    """Дата публикации / meta (возвращает aware UTC)."""
    if not raw:
        return None
    text = str(raw).strip()
    schema = parse_schema_start_date(text, geo=geo)
    if schema:
        return schema
    if "T" in text or re.search(r"\d{4}-\d{2}-\d{2}", text):
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return to_storage_datetime(dt, geo=geo)
        except ValueError:
            pass
    d = _parse_named_month_date(text, _months_for_geo(geo))
    if d:
        return default_kickoff_storage(d, hour=0, minute=0, geo=geo)
    return None


# Обратная совместимость импортов
default_kickoff_utc = default_kickoff_storage


def parse_match_datetime(
    text: str,
    *,
    url: Optional[str] = None,
    source_tz: Optional[str] = None,
    geo: Optional[str] = None,
) -> Optional[datetime]:
    """
    Дата/время матча со страницы → aware UTC.
    Текст без TZ (рум. месяцы, schema.org) трактуется как source_tz.
    """
    if not text:
        text = ""
    schema = parse_schema_start_date(text, source_tz=source_tz, geo=geo)
    if schema:
        return schema

    if "T" in text and re.search(r"\d{2}:\d{2}", text):
        parsed = parse_date(text)
        if parsed:
            return parsed

    from src.scraper.utils.match_datetime import get_source_zoneinfo

    tz = ZoneInfo(source_tz) if source_tz else get_source_zoneinfo(geo)

    m_dot = re.search(
        r"(\d{1,2})\.(\d{1,2})\.(\d{4})(?:\s+(\d{1,2}):(\d{2}))?",
        text,
    )
    if m_dot:
        day_s, mo_s, year_s, hour_s, minute_s = m_dot.groups()
        hour = int(hour_s) if hour_s else 12
        minute = int(minute_s) if minute_s else 0
        local = datetime(
            int(year_s),
            int(mo_s),
            int(day_s),
            hour,
            minute,
            tzinfo=tz,
        )
        return local.astimezone(STORAGE_TZ)

    months = _months_for_geo(geo)
    month_pat = "|".join(sorted(months.keys(), key=len, reverse=True))
    m = re.search(
        rf"(\d{{1,2}})\s+({month_pat})(?:\s+(\d{{4}}))?,?\s*(\d{{1,2}}):(\d{{2}})",
        text,
        re.I,
    )
    if m:
        day_s, month_name, year_s, hour_s, minute_s = m.groups()
        month = months.get(month_name.lower())
        if month:
            year = int(year_s) if year_s else date.today().year
            local = datetime(
                year, month, int(day_s), int(hour_s), int(minute_s), tzinfo=tz
            )
            return local.astimezone(STORAGE_TZ)

    d = _parse_named_month_date(text, months)
    if d:
        return default_kickoff_storage(d, source_tz=source_tz, geo=geo)

    if url:
        slug_d = parse_date_from_url(url, geo=geo)
        if slug_d:
            return default_kickoff_storage(slug_d, source_tz=source_tz, geo=geo)
    return None


def is_upcoming_match(match_date: Optional[datetime], *, grace_hours: int = 6) -> bool:
    from src.scraper.utils.match_datetime import is_upcoming_match as _is_upcoming

    return _is_upcoming(match_date, grace_hours=grace_hours)


def parse_date_from_url(url: str, *, geo: Optional[str] = None) -> Optional[date]:
    """Извлечь дату из slug (29-martie-2026, 4-iyunya-2026, 02-06-2026)."""
    slug = url.rstrip("/").split("/")[-1].lower()
    months = _months_for_geo(geo)
    m = re.search(r"(\d{1,2})-(" + "|".join(sorted(months.keys(), key=len, reverse=True)) + r")-(\d{4})", slug)
    if m:
        day, month_name, year = m.groups()
        month = months.get(month_name)
        if month:
            return date(int(year), month, int(day))
    m = re.search(r"(\d{2})-(\d{2})-(\d{4})", slug)
    if m:
        d, mo, y = m.groups()
        return date(int(y), int(mo), int(d))
    return None
