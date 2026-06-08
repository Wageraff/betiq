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
from src.scraper.utils.url_dates import (
    RO_MONTHS,
    RU_MONTHS,
    months_for_geo,
    parse_date_from_url,
)

_months_for_geo = months_for_geo


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
    "nhl": "hockey",
    "нхл": "hockey",
    "кхл": "hockey",
    "рпл": "football",
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

_MMA_COMPETITION_RE = re.compile(
    r"\b(ufc|bellator|pfl|one\s+championship|mma|bare\s+knuckle)\b", re.I
)

_CYRILLIC_RE = re.compile(r"[\u0400-\u04FF]")

_COMPETITION_CANONICAL_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"чм|world\s*cup|fifa\s*world", re.I), "World Cup"),
    (re.compile(r"champions\s*league|лч\b|liga\s*campionilor", re.I), "UEFA Champions League"),
    (re.compile(r"europa\s*league|ле\b|liga\s*europa", re.I), "UEFA Europa League"),
    (re.compile(r"\bnhl\b|нхл\b", re.I), "NHL"),
    (re.compile(r"\bnba\b", re.I), "NBA"),
    (re.compile(r"рпл|rpl|premier\s*league.*russia", re.I), "Premier League"),
    (re.compile(r"la\s*liga|испан", re.I), "La Liga"),
    (re.compile(r"bundesliga|бундес", re.I), "Bundesliga"),
    (re.compile(r"serie\s*a|серия\s*а", re.I), "Serie A"),
    (re.compile(r"ligue\s*1", re.I), "Ligue 1"),
    (re.compile(r"friendl|товарищ", re.I), "Friendlies"),
]

ALLOWED_BET_TYPES = frozenset({
    "1x2",
    "1X2",
    "winner",
    "total",
    "totals",
    "both_teams_score",
    "btts",
    "handicap",
    "double_chance",
    "draw_no_bet",
})

_ALLOWED_BET_TYPES_LOWER = {b.lower() for b in ALLOWED_BET_TYPES}


def is_allowed_bet_type(bet_type: str | None) -> bool:
    if not bet_type or not str(bet_type).strip():
        return True
    return str(bet_type).lower().strip() in _ALLOWED_BET_TYPES_LOWER


def canonical_competition_name(competition: Optional[str]) -> Optional[str]:
    """Русские/смешанные названия турниров → EN (до AF-link)."""
    if not competition or not str(competition).strip():
        return competition
    text = str(competition).strip()
    for pattern, name in _COMPETITION_CANONICAL_RULES:
        if pattern.search(text):
            return name
    if _CYRILLIC_RE.search(text):
        return text
    return text


def infer_sport_from_competition(competition: Optional[str]) -> Optional[str]:
    """Вид спорта по названию турнира (UFC → mma, ЧМ → football, …)."""
    if not competition:
        return None
    if _MMA_COMPETITION_RE.search(competition):
        return "mma"
    if re.search(r"world\s*cup|чм|fifa\s*world", competition, re.I):
        return "football"
    if re.search(r"\bnhl\b|нхл\b|кхл\b", competition, re.I):
        return "hockey"
    if re.search(r"\bnba\b|wnba\b|euroleague", competition, re.I):
        return "basketball"
    if re.search(
        r"champions\s*league|europa\s*league|premier\s*league|la\s*liga|"
        r"bundesliga|serie\s*a|ligue\s*1|рпл|eredivisie",
        competition,
        re.I,
    ):
        return "football"
    if re.search(r"\batp\b|\bwta\b|wimbledon|roland|open\b", competition, re.I):
        return "tennis"
    return None


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


