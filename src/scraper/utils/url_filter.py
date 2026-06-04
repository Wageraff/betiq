"""Отбор URL статей до page.goto — только с датой в slug и матч сегодня или позже."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from src.scraper.utils.normalizer import parse_date_from_url


def is_scrapeable_article_url(
    url: str,
    *,
    max_days: int,
    geo: Optional[str] = None,
) -> bool:
    """
    True — парсер может открывать URL.
    False — прошлые дни в slug, слишком далёкое будущее или нет распознанной даты.
    """
    d = parse_date_from_url(url, geo=geo)
    if d is None:
        return False
    today = date.today()
    if d < today:
        return False
    if d > today + timedelta(days=max_days):
        return False
    return True


def filter_scrape_urls(
    urls: list[str],
    *,
    max_days: int,
    geo: Optional[str] = None,
) -> list[str]:
    return [u for u in urls if is_scrapeable_article_url(u, max_days=max_days, geo=geo)]
