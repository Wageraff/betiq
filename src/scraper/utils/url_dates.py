"""Дата матча из slug URL — только stdlib (без config/pydantic)."""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

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
    "iyunja": 6,
    "iyunia": 6,
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


def months_for_geo(geo: Optional[str] = None) -> dict[str, int]:
    if geo and geo.upper() == "RU":
        merged = dict(RO_MONTHS)
        merged.update(RU_MONTHS)
        return merged
    return RO_MONTHS


def parse_date_from_url(url: str, *, geo: Optional[str] = None) -> Optional[date]:
    """Извлечь дату из slug (29-martie-2026, 4-iyunya-2026, 02-06-2026)."""
    slug = url.rstrip("/").split("/")[-1].lower()
    months = months_for_geo(geo)
    m = re.search(
        r"(\d{1,2})-(" + "|".join(sorted(months.keys(), key=len, reverse=True)) + r")-(\d{4})",
        slug,
    )
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
