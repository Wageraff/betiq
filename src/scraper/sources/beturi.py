"""Парсер beturi.ro — ponturi pariuri."""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

from playwright.async_api import Page

from src.scraper.utils.browser import wait_cloudflare
from src.scraper.utils.normalizer import (
    default_kickoff_storage,
    normalize_sport,
    parse_date,
    parse_date_from_url,
    parse_match_datetime,
    parse_odds,
)
from src.scraper.utils.teams import parse_teams_from_title

SOURCE_CONFIG = {
    "name": "beturi.ro",
    "base_url": "https://beturi.ro",
    "category_url": "/ponturi-pariuri/",
    "language": "ro",
    "geo": "RO",
}

_SPORT_FOLDERS = frozenset(
    {"fotbal", "tenis", "baschet", "handbal", "hochei", "ufc", "formula-1"}
)
_SKIP_SEGMENTS = frozenset({"page", "feed", "wp-json"})

_COLLECT_URLS_JS = """
() => {
  const sports = new Set(%(sports)s);
  const skip = new Set(%(skip)s);
  const out = new Set();
  for (const a of document.querySelectorAll('a[href]')) {
    let href = a.href.split('#')[0].split('?')[0].replace(/\\/$/, '');
    if (!href.includes('beturi.ro/ponturi-pariuri/')) continue;
    let path;
    try { path = new URL(href).pathname; } catch (e) { continue; }
    const parts = path.split('/').filter(Boolean);
    if (parts.length < 2 || parts[0] !== 'ponturi-pariuri') continue;
    if (skip.has(parts[1])) continue;
    if (sports.has(parts[1])) {
      if (parts.length >= 4) out.add(href);
      continue;
    }
    if (parts.length === 2) out.add(href);
  }
  return [...out];
}
""" % {
    "sports": json.dumps(list(_SPORT_FOLDERS)),
    "skip": json.dumps(list(_SKIP_SEGMENTS)),
}

_PARSE_JS = """
() => {
  const h1 = document.querySelector('h1')?.innerText?.trim() || '';
  const metaDate = document.querySelector('time[datetime]')?.getAttribute('datetime')
    || document.querySelector('meta[property="article:published_time"]')?.content
    || '';
  const author = document.querySelector('.author a, .post-author a, [rel="author"]')
    ?.textContent?.trim() || '';
  const competition = document.querySelector('.breadcrumb li:last-child, .league-name')
    ?.textContent?.trim() || '';
  let sport = '';
  const cats = document.querySelector('.post-categories, .entry-categories');
  if (cats) sport = cats.textContent.trim();

  const contentEl = document.querySelector('article .entry-content, article, .post-content, main article');
  const full_text = contentEl ? contentEl.innerText.trim() : '';

  let team_home = '', team_away = '';
  const cleanH1 = h1.replace(/\\s+ponturi.*$/i, '').trim();
  const vsMatch = cleanH1.match(/^(.+?)\\s+vs\\s+(.+)$/i);
  if (vsMatch) {
    team_home = vsMatch[1].trim();
    team_away = vsMatch[2].trim();
  } else {
    const dashMatch = cleanH1.match(/^(.+?)\\s+[—–]\\s+(.+)$/);
    if (dashMatch) {
      team_home = dashMatch[1].trim();
      team_away = dashMatch[2].trim();
    }
  }
  let kickoff = document.querySelector('time[datetime]')?.getAttribute('datetime') || '';

  const bets = [];
  const oddsEls = document.querySelectorAll('.odds, .cotă, .cota, [class*="odd"]');
  const pickEl = document.querySelector('.tip-pick, .bet-pick, .pont');
  const mainOdds = document.querySelector('.main-odd, .primary-odd');
  if (pickEl || mainOdds || oddsEls.length) {
    bets.push({
      bet_type: '1X2',
      bet_pick: pickEl?.textContent?.trim() || '',
      odds: mainOdds?.textContent?.trim() || oddsEls[0]?.textContent?.trim() || '',
      is_main: true,
    });
  }

  return { h1, metaDate, author, competition, sport, kickoff, full_text, team_home, team_away, bets };
}
"""


async def get_article_urls(page: Page) -> list[str]:
    url = SOURCE_CONFIG["base_url"] + SOURCE_CONFIG["category_url"]
    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    await wait_cloudflare(page)
    urls = await page.evaluate(_COLLECT_URLS_JS)
    return sorted(set(urls))


def _infer_sport_from_url(url: str) -> Optional[str]:
    path = urlparse(url).path.lower()
    for folder in _SPORT_FOLDERS:
        if f"/ponturi-pariuri/{folder}/" in path:
            return normalize_sport(folder.replace("-", " "))
    return normalize_sport("fotbal")


async def parse_prediction(page: Page, url: str) -> Optional[dict]:
    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    await wait_cloudflare(page)

    raw = await page.evaluate(_PARSE_JS)
    if not raw or not raw.get("h1"):
        return None

    title = raw["h1"]
    team_home = raw.get("team_home") or ""
    team_away = raw.get("team_away") or ""

    if not team_home or not team_away:
        team_home, team_away = parse_teams_from_title(title)

    full_text = raw.get("full_text") or ""
    geo = SOURCE_CONFIG.get("geo")
    match_date = parse_match_datetime(
        raw.get("kickoff") or raw.get("metaDate") or full_text[:1200],
        url=url,
        geo=geo,
    )
    if not match_date:
        match_date = parse_date(raw.get("metaDate"))
    if not match_date:
        d = parse_date_from_url(url)
        if d:
            match_date = default_kickoff_storage(d, geo=geo)

    published_at = match_date
    bets = []
    for i, b in enumerate(raw.get("bets") or []):
        odds = parse_odds(b.get("odds"))
        if b.get("bet_pick") or odds:
            bets.append(
                {
                    "bet_type": b.get("bet_type") or "1X2",
                    "bet_pick": b.get("bet_pick") or "",
                    "odds": odds,
                    "is_main": b.get("is_main", i == 0),
                }
            )

    return {
        "source_url": url,
        "title": title,
        "team_home": team_home,
        "team_away": team_away,
        "sport": normalize_sport(raw.get("sport")) or _infer_sport_from_url(url),
        "competition": raw.get("competition") or "",
        "match_date": match_date,
        "author": raw.get("author") or "",
        "full_text": raw.get("full_text") or "",
        "published_at": published_at,
        "bets": bets,
    }
