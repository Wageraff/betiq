"""Парсер beturi.ro — разделы ponturi-pariuri по видам спорта.

См. instructions/beturi.md: card-ponturi, хлебные крошки, div.row.content.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urlparse

from src.scraper.utils.html_clean import clean_article_html, html_to_plain_text
from src.scraper.utils.normalizer import (
    default_kickoff_storage,
    normalize_sport,
    parse_date,
    parse_date_from_url,
    parse_match_datetime,
    parse_odds,
)
from src.scraper.utils.teams import parse_teams_from_title

log = logging.getLogger("beturi")

SOURCE_CONFIG = {
    "name": "beturi.ro",
    "base_url": "https://beturi.ro",
    "category_url": "/ponturi-pariuri/fotbal/",
    "language": "ro",
    "geo": "RO",
}

BETURI_SECTIONS: list[dict[str, Any]] = [
    {"key": "fotbal", "path": "/ponturi-pariuri/fotbal/", "sport": "football"},
    {"key": "tenis", "path": "/ponturi-pariuri/tenis/", "sport": "tennis"},
    {"key": "baschet", "path": "/ponturi-pariuri/baschet/", "sport": "basketball"},
    {"key": "handbal", "path": "/ponturi-pariuri/handbal/", "sport": "handball"},
    {"key": "hochei", "path": "/ponturi-pariuri/hochei/", "sport": "hockey"},
]

_URL_SPORT_HINT: dict[str, str] = {}

_SPORT_CRUMB_MAP = {
    "fotbal": "football",
    "tenis": "tennis",
    "baschet": "basketball",
    "handbal": "handball",
    "hochei": "hockey",
    "volei": "volleyball",
}

_TEST_URLS = [
    (
        "football",
        "https://beturi.ro/ponturi-pariuri/fotbal/international/olanda-algeria-amical-03-06-2026/",
    ),
    (
        "tennis",
        "https://beturi.ro/ponturi-pariuri/tenis/sabalenka-shnaider-roland-garros-03-06-2026/",
    ),
]

_SKIP_URL = re.compile(r"/page/|\?page=|/feed/|wp-json", re.I)
_ARTICLE_DATE = re.compile(r"\d{2}-\d{2}-\d{4}|\d{1,2}-[a-z]+-\d{4}", re.I)

_COLLECT_JS = """
(sportKey) => {
  const skip = /\\/page\\/|\\?page=/i;
  const out = new Set();
  for (const a of document.querySelectorAll('a[href]')) {
    let href = a.href.split('#')[0].split('?')[0].replace(/\\/$/, '');
    if (!href.includes('beturi.ro/ponturi-pariuri/' + sportKey + '/')) continue;
    if (skip.test(href)) continue;
    let path;
    try { path = new URL(href).pathname; } catch (e) { continue; }
    const parts = path.split('/').filter(Boolean);
    if (parts.length < 4 || parts[0] !== 'ponturi-pariuri' || parts[1] !== sportKey) continue;
    if (!/\\d{2}-\\d{2}-\\d{4}|\\d{1,2}-[a-z]+-\\d{4}/i.test(parts[parts.length - 1])) continue;
    out.add(href);
  }
  return [...out];
}
"""

_PARSE_JS = """
() => {
  const getMeta = (sel) => document.querySelector(sel)?.getAttribute('content')?.trim() || '';
  const meta = {
    title: getMeta('meta[property="og:title"]') || document.title || '',
    description: getMeta('meta[property="og:description"]') || getMeta('meta[name="description"]'),
  };

  const h1 = document.querySelector('h1')?.innerText?.trim() || '';

  let author = document.querySelector('.authorTop a.text--blue, .authorTop a')?.textContent?.trim() || '';
  if (!author) {
    author = document.querySelector('.grand-forecast__author-name')?.textContent?.trim() || '';
  }

  const breadcrumbs = [];
  const crumbRoot = document.querySelector('#breadcrumbs, .breadcrumb, nav.breadcrumb');
  if (crumbRoot) {
    for (const a of crumbRoot.querySelectorAll('a')) {
      const text = a.textContent?.trim();
      if (text) breadcrumbs.push({ text, href: a.href || '' });
    }
  }

  const card = document.querySelector('div.card-ponturi');
  let competition = '';
  let matchDay = '';
  let venue = '';
  let matchTime = '';
  const bets = [];

  if (card) {
    const compEl = card.querySelector('div.text-start');
    if (compEl) competition = compEl.innerText?.trim() || '';

    const dayEl = card.querySelector('div.fs--14.font-weight-bold, div.font-weight-bold.fs--14');
    if (dayEl) matchDay = dayEl.innerText?.trim() || '';

    const venueEl = card.querySelector('div.fs--12.align-self-center, div.fs--12.font--arial');
    if (venueEl) venue = venueEl.innerText?.trim() || '';

    const tvEl = card.querySelector('.card-ponturi__tv');
    if (tvEl) matchTime = tvEl.innerText?.trim() || '';

    const pick = card.querySelector('.card-ponturi__cota-text')?.textContent?.trim() || '';
    const oddsEl = card.querySelector('.text-center.fs--28, .fs--28.fw--bold.text--blue');
    const odds = oddsEl?.textContent?.trim() || '';
    if (pick || odds) {
      bets.push({ bet_type: '1X2', bet_pick: pick, odds, is_main: true });
    }
  }

  let contentHtml = '';
  const contentRoot = document.querySelector('div.row.content');
  if (contentRoot) {
    const clone = contentRoot.cloneNode(true);
    clone.querySelectorAll(
      '.d-flex.flex-row.align-items-center.text--caption, .kk-star-ratings, .kk-star-ratings'
    ).forEach((el) => el.remove());
    contentHtml = clone.innerHTML;
  }

  const metaDate = document.querySelector('time[datetime]')?.getAttribute('datetime')
    || getMeta('meta[property="article:published_time"]')
    || '';

  return {
    h1,
    meta,
    metaDate,
    author,
    breadcrumbs,
    competition,
    matchDay,
    venue,
    matchTime,
    bets,
    content_html: contentHtml,
  };
}
"""


def _is_valid_article_url(url: str) -> bool:
    if _SKIP_URL.search(url):
        return False
    path = urlparse(url).path
    parts = [p for p in path.split("/") if p]
    if len(parts) < 4 or parts[0] != "ponturi-pariuri":
        return False
    return bool(_ARTICLE_DATE.search(parts[-1]))


def _sport_from_breadcrumbs(raw: dict) -> Optional[str]:
    crumbs = raw.get("breadcrumbs") or []
    texts = [c.get("text", "") for c in crumbs if isinstance(c, dict)]
    for i, t in enumerate(texts):
        if re.search(r"ponturi\s*pariuri", t, re.I) and i + 2 < len(texts):
            sport_text = texts[i + 2].strip().lower()
            return normalize_sport(_SPORT_CRUMB_MAP.get(sport_text, sport_text))
    if len(texts) >= 3:
        sport_text = texts[2].strip().lower()
        return normalize_sport(_SPORT_CRUMB_MAP.get(sport_text, sport_text))
    return None


def _infer_sport_from_url(url: str) -> Optional[str]:
    path = urlparse(url).path.lower()
    for folder, sport in _SPORT_CRUMB_MAP.items():
        if f"/ponturi-pariuri/{folder}/" in path:
            return sport
    return None


def _build_kickoff_text(raw: dict) -> str:
    day = (raw.get("matchDay") or "").strip()
    tv = (raw.get("matchTime") or "").strip()
    time_part = ""
    if tv:
        m = tv.match(r"(\d{1,2}:\d{2})")
        if m:
            time_part = m.group(1)
    if day and time_part:
        return f"{day} {time_part}"
    return day or tv


def _build_match_date(raw: dict, url: str) -> Optional[datetime]:
    geo = SOURCE_CONFIG.get("geo")
    kickoff = _build_kickoff_text(raw)
    dt = parse_match_datetime(kickoff, url=url, geo=geo)
    if dt:
        return dt
    dt = parse_date(raw.get("metaDate"))
    if dt:
        return dt
    d = parse_date_from_url(url)
    return default_kickoff_storage(d, geo=geo) if d else None


def _parse_bets(raw_bets: list) -> list[dict]:
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for b in raw_bets or []:
        pick = (b.get("bet_pick") or "").strip()
        odds = parse_odds(b.get("odds"))
        key = (pick, str(odds) if odds else "")
        if key in seen:
            continue
        seen.add(key)
        if not pick and not odds:
            continue
        out.append(
            {
                "bet_type": b.get("bet_type") or "1X2",
                "bet_pick": pick,
                "odds": odds,
                "is_main": b.get("is_main", len(out) == 0),
            }
        )
    return out


def _is_valid_teams(home: str, away: str) -> bool:
    if not home or not away or len(home) < 2 or len(away) < 2:
        return False
    junk = re.compile(r"^ponturi$|^cote$|^pariuri$", re.I)
    return not (junk.search(home) or junk.search(away))


async def get_article_urls(page: Any) -> list[str]:
    from src.scraper.utils.browser import wait_cloudflare

    global _URL_SPORT_HINT
    _URL_SPORT_HINT = {}
    base = SOURCE_CONFIG["base_url"].rstrip("/")
    found: set[str] = set()

    for section in BETURI_SECTIONS:
        url = base + section["path"]
        log.info("Collect URLs: %s (%s)", section["key"], url)
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await wait_cloudflare(page)
        urls = await page.evaluate(_COLLECT_JS, section["key"])
        for u in urls:
            u = u.split("#")[0].split("?")[0].rstrip("/")
            if not _is_valid_article_url(u):
                continue
            found.add(u)
            _URL_SPORT_HINT[u] = section["sport"]

    return sorted(found)


async def parse_prediction(page: Any, url: str) -> Optional[dict]:
    from src.scraper.utils.browser import wait_cloudflare

    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    await wait_cloudflare(page)

    raw = await page.evaluate(_PARSE_JS) or {}
    title = raw.get("h1") or ""
    if not title:
        return None

    team_home, team_away = parse_teams_from_title(title)
    if not _is_valid_teams(team_home, team_away):
        log.warning("Skip %s: invalid teams %r vs %r", url, team_home, team_away)
        return None

    match_date = _build_match_date(raw, url)
    if not match_date:
        log.warning("Skip %s: no match_date", url)
        return None

    sport = _sport_from_breadcrumbs(raw) or _URL_SPORT_HINT.get(url.rstrip("/"))
    if not sport:
        sport = _infer_sport_from_url(url)
    if not sport:
        log.warning("Skip %s: could not resolve sport", url)
        return None

    content_html = raw.get("content_html") or ""
    full_text = html_to_plain_text(clean_article_html(content_html))

    bets = _parse_bets(raw.get("bets"))
    competition = (raw.get("competition") or "").strip()
    venue = (raw.get("venue") or "").strip()
    if venue and competition:
        competition = f"{competition} — {venue}"

    return {
        "source_url": url,
        "title": title,
        "team_home": team_home,
        "team_away": team_away,
        "sport": sport,
        "competition": competition,
        "match_date": match_date,
        "author": (raw.get("author") or "").strip(),
        "full_text": full_text,
        "published_at": parse_date(raw.get("metaDate")) or match_date,
        "bets": bets,
        "meta": raw.get("meta"),
        "content_html": clean_article_html(content_html),
    }


async def run_test_parse(urls: Optional[list[tuple[str, str]]] = None) -> None:
    """Тестовый прогон URL из instructions/beturi.md."""
    from src.scraper.utils.browser import browser_lifecycle, page_session

    pairs = urls or _TEST_URLS
    async with browser_lifecycle():
        async with page_session() as (page, _proxy):
            for expected_sport, url in pairs:
                print(f"\n{'=' * 60}\n{url}\n")
                data = await parse_prediction(page, url)
                if not data:
                    print("  FAIL: parse returned None")
                    continue
                ok_sport = data["sport"] == expected_sport
                print(f"  teams:      {data['team_home']} vs {data['team_away']}")
                print(f"  sport:      {data['sport']} (expected {expected_sport}) {'OK' if ok_sport else 'MISMATCH'}")
                print(f"  competition:{data.get('competition')}")
                print(f"  match_date: {data['match_date']}")
                print(f"  author:     {data.get('author')}")
                print(f"  bets:       {len(data.get('bets') or [])}")
                for b in data.get("bets") or []:
                    print(f"    - {b.get('bet_pick')} @ {b.get('odds')}")
                print(f"  text_len:   {len(data.get('full_text') or '')}")
                preview = (data.get("full_text") or "")[:200].replace("\n", " ")
                print(f"  preview:    {preview}...")


def main() -> None:
    from src.config import setup_logging

    setup_logging()
    parser = argparse.ArgumentParser(description="Beturi parser tests")
    parser.add_argument("--test", action="store_true", help="Parse example URLs from instructions")
    parser.add_argument("--url", action="append", help="Extra URL to test (can repeat)")
    args = parser.parse_args()
    if args.test or args.url:
        extra = [("", u) for u in (args.url or [])]
        asyncio.run(run_test_parse(_TEST_URLS + extra if args.test else extra))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
