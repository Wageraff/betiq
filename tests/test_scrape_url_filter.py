"""
Фильтр URL перед парсингом статей.

Запуск на сервере (из /opt/betiq):
  export PYTHONPATH=/opt/betiq
  ./venv/bin/python3.11 -m unittest tests.test_scrape_url_filter -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from datetime import date, timedelta
from src.scraper.utils.url_filter import filter_scrape_urls, is_scrapeable_article_url


class ScrapeUrlFilterTests(unittest.TestCase):
    def test_rejects_past_slug_date(self) -> None:
        past = date.today() - timedelta(days=3)
        slug = past.strftime("%d-%m-%Y")
        url = f"https://legalbet.ru/match-center/team-a-team-b-{slug}/"
        self.assertFalse(is_scrapeable_article_url(url, max_days=7, geo="RU"))

    def test_accepts_today_and_future_within_window(self) -> None:
        today = date.today()
        slug = today.strftime("%d-%m-%Y")
        url = f"https://legalbet.ru/ponturi/x-ponturi-pariuri-{slug}-author/"
        self.assertTrue(is_scrapeable_article_url(url, max_days=7, geo="RU"))
        future = today + timedelta(days=3)
        fslug = future.strftime("%d-%m-%Y")
        url2 = f"https://beturi.ro/ponturi-pariuri/fotbal/x-{fslug}/"
        self.assertTrue(is_scrapeable_article_url(url2, max_days=7))

    def test_rejects_too_far_future(self) -> None:
        far = date.today() + timedelta(days=30)
        slug = far.strftime("%d-%m-%Y")
        url = f"https://legalbet.ro/ponturi/x-ponturi-pariuri-{slug}-a/"
        self.assertFalse(is_scrapeable_article_url(url, max_days=7, geo="RU"))

    def test_rejects_url_without_date(self) -> None:
        self.assertFalse(
            is_scrapeable_article_url(
                "https://example.com/prognozy/team-vs-team-prognoz/",
                max_days=7,
            )
        )

    def test_filter_scrape_urls(self) -> None:
        today_slug = date.today().strftime("%d-%m-%Y")
        past_slug = (date.today() - timedelta(days=1)).strftime("%d-%m-%Y")
        urls = [
            f"https://legalbet.ru/ponturi/a-ponturi-pariuri-{today_slug}-x/",
            f"https://legalbet.ru/ponturi/b-ponturi-pariuri-{past_slug}-x/",
            "https://legalbet.ru/ponturi/no-date/",
        ]
        out = filter_scrape_urls(urls, max_days=7, geo="RU")
        self.assertEqual(len(out), 1)
        self.assertIn(today_slug, out[0])


if __name__ == "__main__":
    unittest.main()
