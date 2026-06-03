"""Парсер pontul-zilei.com — ponturi pariuri."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from playwright.async_api import Page

from src.scraper.utils.browser import wait_cloudflare
from src.scraper.utils.normalizer import (
    default_kickoff_utc,
    normalize_sport,
    parse_date,
    parse_date_from_url,
    parse_match_datetime,
    parse_odds,
)
from src.scraper.utils.teams import parse_teams_from_title

SOURCE_CONFIG = {
    "name": "pontul-zilei.com",
    "base_url": "https://www.pontul-zilei.com",
    "category_url": "/category/ponturi-pariuri/",
    "language": "ro",
    "geo": "RO",
}

_COLLECT_URLS_JS = """
() => {
  const out = new Set();
  for (const a of document.querySelectorAll('a[href*="/ponturipariuri/"]')) {
    let href = a.href.split('#')[0].split('?')[0].replace(/\\/$/, '');
    if (href.includes('/author/')) continue;
    const slug = href.split('/').pop() || '';
    if (slug.length < 8) continue;
    out.add(href);
  }
  return [...out];
}
"""

_PARSE_JS = """
() => {
  const h1 = document.querySelector('h1')?.innerText?.trim() || '';
  const bodyText = document.body?.innerText || '';
  const addedMatch = bodyText.match(/Adaugat:\\s*([^\\n]+)/i);
  const metaDate = document.querySelector('time[datetime]')?.getAttribute('datetime')
    || (addedMatch ? addedMatch[1] : '');
  const authorMatch = bodyText.match(/Tipster:\\s*([^\\n]+)/i);
  const author = authorMatch ? authorMatch[1].trim() : '';

  let competition = '';
  const catMatch = bodyText.match(/Categorii:\\s*([^\\n]+)/i);
  if (catMatch) competition = catMatch[1].split(',')[0].trim();

  const contentEl = document.querySelector('.entry-content, article .content, article');
  const full_text = contentEl ? contentEl.innerText.trim() : '';

  let team_home = '', team_away = '', sport = 'football';
  const cleanH1 = h1.replace(/\\s+ponturi.*$/i, '').trim();
  const vsInH1 = cleanH1.match(/^(.+?)\\s+vs\\s+(.+)$/i);
  if (vsInH1) {
    team_home = vsInH1[1].trim();
    team_away = vsInH1[2].trim();
  } else {
    const dashInH1 = cleanH1.match(/^(.+?)\\s+[—–]\\s+(.+)$/);
    if (dashInH1) {
      team_home = dashInH1[1].trim();
      team_away = dashInH1[2].trim();
    }
  }
  let kickoff = metaDate || '';

  const bets = [];
  const blocks = [...document.querySelectorAll('.entry-content, article')];
  const root = blocks[0] || document.body;
  const lines = (root.innerText || '').split('\\n').map(l => l.trim()).filter(Boolean);

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const vs = line.match(/^(.+?)\\s+vs\\s+(.+)$/i);
    if (vs && !team_home) {
      team_home = vs[1].trim();
      team_away = vs[2].trim();
    }
    if (/^fotbal$/i.test(line)) sport = 'fotbal';
    if (/^tenis$/i.test(line)) sport = 'tenis';
    if (/^baschet$/i.test(line)) sport = 'baschet';
    const pickMatch = line.match(/^\\*\\*(.+?)\\*\\*$/);
    if (pickMatch && team_home) {
      let odds = null;
      for (let j = i + 1; j < Math.min(i + 6, lines.length); j++) {
        const o = lines[j].match(/^[\\d]+[.,][\\d]+$/);
        if (o) { odds = o[0]; break; }
      }
      bets.push({
        bet_type: '1X2',
        bet_pick: pickMatch[1].trim(),
        odds: odds,
        is_main: bets.length === 0,
      });
      if (bets.length >= 3) break;
    }
  }

  if (!team_home) {
    const m = full_text.match(/([A-Za-zÀ-ÿ0-9 .'-]+)\\s+vs\\s+([A-Za-zÀ-ÿ0-9 .'-]+)/i);
    if (m) {
      team_home = m[1].trim();
      team_away = m[2].trim();
    }
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
    if not team_home or not team_away:
        return None

    full_text = raw.get("full_text") or ""
    match_date = parse_match_datetime(
        raw.get("kickoff") or raw.get("metaDate") or full_text[:1200],
        url=url,
    )
    if not match_date:
        match_date = parse_date(raw.get("metaDate"))
    if not match_date:
        d = parse_date_from_url(url)
        if d:
            match_date = default_kickoff_utc(d)

    if not match_date:
        return None

    bets = []
    for i, b in enumerate(raw.get("bets") or []):
        odds = parse_odds(b.get("odds"))
        pick = (b.get("bet_pick") or "").strip()
        if pick or odds:
            bets.append(
                {
                    "bet_type": b.get("bet_type") or "1X2",
                    "bet_pick": pick,
                    "odds": odds,
                    "is_main": b.get("is_main", i == 0),
                }
            )

    return {
        "source_url": url,
        "title": title,
        "team_home": team_home,
        "team_away": team_away,
        "sport": normalize_sport(raw.get("sport")),
        "competition": raw.get("competition") or "",
        "match_date": match_date,
        "author": raw.get("author") or "",
        "full_text": raw.get("full_text") or "",
        "published_at": parse_date(raw.get("metaDate")) or match_date,
        "bets": bets,
    }
