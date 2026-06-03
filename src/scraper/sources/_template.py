"""
Шаблон парсера источника. Скопировать файл, заполнить селекторы, добавить запись в sources.
"""
from __future__ import annotations

from playwright.async_api import Page

from src.scraper.utils.browser import wait_cloudflare
from src.scraper.utils.normalizer import normalize_sport, parse_date, parse_odds

SOURCE_CONFIG = {
    "name": "SITE_NAME",
    "base_url": "https://example.com",
    "category_url": "/ponturi/",
    "language": "ro",
    "geo": "RO",
}


async def get_article_urls(page: Page) -> list[str]:
    await page.goto(SOURCE_CONFIG["base_url"] + SOURCE_CONFIG["category_url"], wait_until="domcontentloaded")
    await wait_cloudflare(page)
    return await page.eval_on_selector_all(
        "SELECTOR a",
        "els => els.map(e => e.href).filter(Boolean)",
    )


async def parse_prediction(page: Page, url: str) -> dict | None:
    await page.goto(url, wait_until="domcontentloaded")
    await wait_cloudflare(page)

    title = await page.eval_on_selector("h1", "el => el?.textContent?.trim() || ''")
    if not title:
        return None

    return {
        "source_url": url,
        "title": title,
        "team_home": "",
        "team_away": "",
        "sport": normalize_sport(""),
        "competition": "",
        "match_date": parse_date(""),
        "author": "",
        "full_text": "",
        "published_at": parse_date(""),
        "bets": [{"bet_type": "1X2", "bet_pick": "", "odds": parse_odds(None), "is_main": True}],
    }
