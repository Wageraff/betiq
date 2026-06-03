"""Парсер legalbet.ro — разделы по видам спорта.

Шаблон страницы (sports_event / forecast) определяется только по разметке на странице,
не по категории сбора. Любой раздел может содержать оба варианта.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Any, Optional

from playwright.async_api import Page

from src.config import setup_logging
from src.scraper.utils.browser import browser_lifecycle, page_session, wait_cloudflare
from src.scraper.utils.html_clean import clean_article_html, html_to_plain_text
from src.scraper.utils.normalizer import (
    default_kickoff_utc,
    normalize_sport,
    parse_date,
    parse_date_from_url,
    parse_match_datetime,
    parse_odds,
)
from src.scraper.utils.teams import parse_teams_from_title

log = logging.getLogger("legalbet")

SOURCE_CONFIG = {
    "name": "legalbet.ro",
    "base_url": "https://legalbet.ro",
    "category_url": "/ponturi/sportul-fotbal/",
    "language": "ro",
    "geo": "RO",
}

# Разделы для сбора (путь → ожидаемый вид спорта)
LEGALBET_SECTIONS: list[dict[str, Any]] = [
    {
        "key": "fotbal",
        "path": "/ponturi/sportul-fotbal/",
        "sport": "football",
        "allow_centrul": True,
    },
    {"key": "tenis", "path": "/ponturi/sportul-tenis/", "sport": "tennis", "allow_centrul": False},
    {
        "key": "baschet",
        "path": "/ponturi/sportul-baschet/",
        "sport": "basketball",
        "allow_centrul": False,
    },
    {
        "key": "handbal",
        "path": "/ponturi/sportul-handbal/",
        "sport": "handball",
        "allow_centrul": False,
    },
    {
        "key": "volei",
        "path": "/ponturi/sportul-volei/",
        "sport": "volleyball",
        "allow_centrul": False,
    },
    {"key": "hochei", "path": "/ponturi/sportul-hochei/", "sport": "hockey", "allow_centrul": False},
]

# URL → sport с страницы раздела (заполняется в get_article_urls)
_URL_SPORT_HINT: dict[str, str] = {}

_SKIP_URL = re.compile(
    r"biletul-zilei|cota-2|/arhiva/|ponturile-de-astazi|/maine/|\?page="
    r"|sferturi-meciuri|cele-mai-bune|pronosticuri-",
    re.I,
)

_TEST_URLS = [
    ("football", "https://legalbet.ro/centrul-de-pariere/dr-congo-denmark-03-06-2026/"),
    ("football", "https://legalbet.ro/ponturi/georgia-romania-ponturi-pariuri-02-06-2026-karbacher/"),
    ("tennis", "https://legalbet.ro/ponturi/matteo-berrettini-matteo-arnaldi-ponturi-pariuri-03-06-2026-vasile-ciobanu/"),
    ("volleyball", "https://legalbet.ro/ponturi/thailanda-f-serbia-f-ponturi-pariuri-03-06-2026-vasile-ciobanu/"),
]

_COLLECT_JS = """
(allowCentrul) => {
  const skip = /biletul-zilei|cota-2|\\/arhiva\\/|ponturile-de-astazi|\\/maine\\/|\\?page=/i;
  const out = new Set();
  for (const a of document.querySelectorAll('a[href]')) {
    let href = a.href.split('#')[0].split('?')[0].replace(/\\/$/, '');
    if (!href.includes('legalbet.ro')) continue;
    if (skip.test(href)) continue;
    if (href.includes('/ponturi/') && href.includes('ponturi-pariuri-')) {
      if (/ponturi-pariuri-\\d{2}-\\d{2}-\\d{4}/i.test(href)) out.add(href);
      continue;
    }
    if (allowCentrul && href.includes('/centrul-de-pariere/')) {
      if (/\\d{2}-\\d{2}-\\d{4}/.test(href)) out.add(href);
    }
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

  const breadcrumbs = [];
  const crumbRoot = document.querySelector('[class*="breadcrumb"], .breadcrumbs');
  if (crumbRoot) {
    const SKIP = new Set(['acasa','acasă','home','ponturi pariuri','ponturi']);
    for (const el of crumbRoot.querySelectorAll('li, a')) {
      const t = (el.textContent || '').trim().replace(/\\s+/g, ' ');
      if (!t || SKIP.has(t.toLowerCase())) continue;
      if (!breadcrumbs.length || breadcrumbs[breadcrumbs.length - 1] !== t) breadcrumbs.push(t);
    }
  }

  // Шаблон страницы — только по DOM, не по URL/категории
  const detectLayout = () => {
    const hasSportsEvent = () => {
      if (document.querySelector('[itemtype*="SportsEvent"]')) return true;
      const start = document.querySelector('meta[itemprop="startDate"]');
      const home = document.querySelector('[itemprop="homeTeam"]');
      const away = document.querySelector('[itemprop="awayTeam"]');
      return !!(start && home && away);
    };
    const hasForecast = () => !!(
      document.querySelector('.forecast-head__names') ||
      document.querySelector('.forecast__text-content[itemprop="articleBody"]') ||
      document.querySelector('.forecast__bets') ||
      document.querySelector('.exp-forecast__header-title')
    );
    if (hasSportsEvent()) return 'sports_event';
    if (hasForecast()) return 'forecast';
    return 'legacy';
  };
  const layout = detectLayout();
  const layoutSignals = {
    sportsEventType: !!document.querySelector('[itemtype*="SportsEvent"]'),
    startDate: !!document.querySelector('meta[itemprop="startDate"]'),
    homeTeam: !!document.querySelector('[itemprop="homeTeam"]'),
    forecastHead: !!document.querySelector('.forecast-head__names'),
    forecastBets: !!document.querySelector('.forecast__bets'),
  };

  let team_home = '', team_away = '', kickoff = '', sport = '', competition = '';
  let author = '', content_html = '', event_meta = {};

  const cleanElText = (el) => {
    if (!el) return '';
    return (el.textContent || '').trim().replace(/\\s+/g, ' ');
  };

  const extractBetsFromCards = (root, cardSel, pickSel, oddsSel) => {
    const bets = [];
    if (!root) return bets;
    for (const card of root.querySelectorAll(cardSel)) {
      const pick = cleanElText(card.querySelector(pickSel));
      const odds = cleanElText(card.querySelector(oddsSel)).replace(',', '.');
      if (!pick || /^ponturi$/i.test(pick) || /^cote$/i.test(pick)) continue;
      if (!odds || !/^[\\d]+[.,][\\d]+$/.test(odds)) continue;
      bets.push({
        bet_type: '1X2',
        bet_pick: pick,
        odds,
        is_main: bets.length === 0,
      });
    }
    return bets;
  };

  const extractForecastBets = () => {
    const root = document.querySelector('.forecast__bets');
    return extractBetsFromCards(
      root,
      '.exp-forecast__bet',
      '.exp-forecast__bet-text',
      '.exp-forecast__coefs-num'
    );
  };

  const extractGrandBets = () => {
    const root = document.querySelector('.grand-forecast__bets');
    if (!root) return [];
    let bets = extractBetsFromCards(
      root,
      '.grand-forecast__bet',
      '.grand-forecast__bet-text',
      '.grand-forecast__coefs-num'
    );
    if (!bets.length) {
      bets = extractBetsFromCards(
        root,
        '.exp-forecast__bet',
        '.exp-forecast__bet-text',
        '.exp-forecast__coefs-num'
      );
    }
    return bets;
  };

  if (layout === 'sports_event') {
    const startEl = document.querySelector('meta[itemprop="startDate"]');
    kickoff = startEl?.getAttribute('content') || '';
    sport = document.querySelector('meta[itemprop="sport"]')?.getAttribute('content') || '';
    team_home = document.querySelector('[itemprop="homeTeam"] meta[itemprop="name"]')?.getAttribute('content')
      || document.querySelector('[itemprop="homeTeam"]')?.textContent?.trim() || '';
    team_away = document.querySelector('[itemprop="awayTeam"] meta[itemprop="name"]')?.getAttribute('content')
      || document.querySelector('[itemprop="awayTeam"]')?.textContent?.trim() || '';
    const loc = document.querySelector('[itemprop="location"] meta[itemprop="name"]')?.getAttribute('content')
      || document.querySelector('[itemprop="address"] meta[itemprop="addressLocality"]')?.getAttribute('content') || '';
    event_meta = {
      startDate: kickoff,
      sport,
      homeTeam: team_home,
      awayTeam: team_away,
      location: loc,
      attendanceMode: document.querySelector('meta[itemprop="eventAttendanceMode"]')?.getAttribute('content') || '',
    };
    author = document.querySelector('.grand-forecast__author-name')?.textContent?.trim()
      || document.querySelector('.exp-forecast__header-title')?.textContent?.trim() || '';
    const htmlEl = document.querySelector('.grand-forecast__text.content-body')
      || document.querySelector('.block-section.block.content-body')
      || document.querySelector('.forecast__text-content[itemprop="articleBody"]')
      || document.querySelector('.forecast__text-content');
    content_html = htmlEl?.innerHTML || '';
    var bets = extractGrandBets();
    if (!bets.length) bets = extractForecastBets();
  } else if (layout === 'forecast') {
    const names = document.querySelector('.forecast-head__names');
    if (names) {
      const vs = names.innerText.split(/\\s+vs\\s+/i);
      if (vs.length === 2) {
        team_home = vs[0].trim();
        team_away = vs[1].trim();
      } else {
        const dash = names.innerText.split(/\\s+[—–]\\s+/);
        if (dash.length === 2) {
          team_home = dash[0].trim();
          team_away = dash[1].trim();
        }
      }
    }
    kickoff = document.querySelector('.forecast-head__info')?.innerText?.trim() || '';
    author = document.querySelector('.exp-forecast__header-title')?.textContent?.trim()
      || document.querySelector('.forecast__author-name')?.textContent?.trim() || '';
    const htmlEl = document.querySelector('.forecast__text-content[itemprop="articleBody"]')
      || document.querySelector('.forecast__text-content');
    content_html = htmlEl?.innerHTML || '';
    var bets = extractForecastBets();
  } else {
    author = document.querySelector('[class*="author"]')?.textContent?.trim() || '';
    content_html = document.querySelector('article')?.innerHTML || '';
    var bets = [];
  }

  const SPORT_KEYS = new Set(['fotbal','tenis','baschet','handbal','hochei','volei']);
  for (let i = 0; i < breadcrumbs.length; i++) {
    const key = breadcrumbs[i].toLowerCase();
    if (SPORT_KEYS.has(key)) {
      sport = sport || key;
      if (breadcrumbs[i + 1] && !SPORT_KEYS.has(breadcrumbs[i + 1].toLowerCase())) {
        competition = breadcrumbs[i + 1];
      }
      break;
    }
  }

  const metaDate = document.querySelector('time[datetime]')?.getAttribute('datetime')
    || document.querySelector('meta[property="article:published_time"]')?.content || '';

  return {
    layout, layoutSignals, h1, meta, metaDate, author, competition, sport, breadcrumbs,
    kickoff, team_home, team_away, content_html, bets, event_meta,
  };
}
"""


def _sport_competition_from_breadcrumbs(crumbs: list[str]) -> tuple[str, str]:
    skip = {"acasa", "acasă", "home", "ponturi pariuri", "ponturi"}
    keys = {"fotbal", "tenis", "baschet", "handbal", "hochei", "volei"}
    items = [c.strip() for c in crumbs if c.strip().lower() not in skip]
    for i, label in enumerate(items):
        key = label.lower()
        if key not in keys:
            continue
        sport = normalize_sport(label) or key
        comp = items[i + 1] if i + 1 < len(items) and items[i + 1].lower() not in keys else ""
        return sport, comp
    return "", ""


def _is_valid_teams(team_home: str, team_away: str) -> bool:
    if not team_home or not team_away or len(team_home) > 70 or len(team_away) > 70:
        return False
    bad = re.compile(r"ponturi\s+pariuri|biletul|cota\s*2|pronostic", re.I)
    return not bad.search(team_home) and not bad.search(team_away)


def _is_valid_article_url(url: str) -> bool:
    if _SKIP_URL.search(url):
        return False
    if "/centrul-de-pariere/" in url:
        return bool(re.search(r"\d{2}-\d{2}-\d{4}", url))
    if "ponturi-pariuri-" in url:
        return bool(re.search(r"ponturi-pariuri-\d{2}-\d{2}-\d{4}", url, re.I))
    return False


def _resolve_sport_and_competition(raw: dict, url: str, layout: str) -> tuple[str, str]:
    """
    Вид спорта: schema SportsEvent → крошки → раздел сбора.
    Раздел не задаёт шаблон, но уточняет sport если на странице нет schema.
    """
    competition = (raw.get("competition") or "").strip()
    bc_sport, bc_comp = _sport_competition_from_breadcrumbs(raw.get("breadcrumbs") or [])
    if bc_comp and not competition:
        competition = bc_comp

    event = raw.get("event_meta") or {}
    schema_sport = normalize_sport(event.get("sport") or "")
    page_sport = normalize_sport(raw.get("sport") or "")
    section = _URL_SPORT_HINT.get(url.rstrip("/"))

    sport = ""
    if layout == "sports_event" and schema_sport:
        sport = schema_sport
    elif page_sport:
        sport = page_sport
    elif bc_sport:
        sport = bc_sport
    elif section:
        sport = section
    elif "/centrul-de-pariere/" in url:
        sport = "football"

    if not sport and section:
        sport = section

    if sport and section and sport != section:
        log.info(
            "Sport: page=%s section_hint=%s url=%s layout=%s",
            sport,
            section,
            url,
            layout,
        )

    return sport, competition


def _build_match_date(raw: dict, url: str) -> Optional[datetime]:
    kickoff = raw.get("kickoff") or raw.get("metaDate") or ""
    event = raw.get("event_meta") or {}
    if event.get("startDate"):
        kickoff = event["startDate"]
    dt = parse_match_datetime(str(kickoff), url=url)
    if dt:
        return dt
    dt = parse_date(raw.get("metaDate"))
    if dt:
        return dt
    d = parse_date_from_url(url)
    return default_kickoff_utc(d) if d else None


_JUNK_PICK = re.compile(r"^ponturi$|^cote$", re.I)


def _parse_bets(raw_bets: list) -> list[dict]:
    out = []
    seen: set[tuple[str, str]] = set()
    for i, b in enumerate(raw_bets or []):
        pick = (b.get("bet_pick") or "").strip()
        if not pick or _JUNK_PICK.match(pick):
            continue
        odds = parse_odds(b.get("odds"))
        if odds is None:
            continue
        key = (pick, str(odds))
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "bet_type": b.get("bet_type") or "1X2",
                "bet_pick": pick,
                "odds": odds,
                "is_main": b.get("is_main", len(out) == 0),
            }
        )
    return out


async def get_article_urls(page: Page) -> list[str]:
    """Обход всех разделов из LEGALBET_SECTIONS."""
    global _URL_SPORT_HINT
    _URL_SPORT_HINT = {}
    base = SOURCE_CONFIG["base_url"].rstrip("/")
    found: set[str] = set()

    for section in LEGALBET_SECTIONS:
        url = base + section["path"]
        log.info("Collect URLs: %s (%s)", section["key"], url)
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await wait_cloudflare(page)
        urls = await page.evaluate(_COLLECT_JS, section.get("allow_centrul", False))
        for u in urls:
            u = u.split("#")[0].split("?")[0].rstrip("/")
            if not _is_valid_article_url(u):
                continue
            found.add(u)
            _URL_SPORT_HINT[u] = section["sport"]

    return sorted(found)


async def parse_prediction(page: Page, url: str) -> Optional[dict]:
    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    await wait_cloudflare(page)

    raw = await page.evaluate(_PARSE_JS) or {}
    layout = raw.get("layout") or "unknown"
    log.info("Parse %s layout=%s signals=%s", url, layout, raw.get("layoutSignals"))
    title = raw.get("h1") or ""
    if not title:
        return None

    team_home = (raw.get("team_home") or "").strip()
    team_away = (raw.get("team_away") or "").strip()
    if not team_home or not team_away:
        team_home, team_away = parse_teams_from_title(title)
    if not _is_valid_teams(team_home, team_away):
        log.warning("Skip %s: invalid teams %r vs %r", url, team_home, team_away)
        return None

    match_date = _build_match_date(raw, url)
    if not match_date:
        return None

    content_html = raw.get("content_html") or ""
    full_text = html_to_plain_text(clean_article_html(content_html))
    if not full_text and content_html:
        full_text = html_to_plain_text(content_html)

    sport, competition = _resolve_sport_and_competition(raw, url, layout)
    if not sport:
        log.warning("Skip %s: could not resolve sport (layout=%s)", url, layout)
        return None

    author = (raw.get("author") or "").strip()
    if not author:
        m = re.search(r"-([a-z]+)/?$", url)
        if m:
            author = m.group(1).replace("-", " ").title()

    bets = _parse_bets(raw.get("bets"))

    event_meta = raw.get("event_meta") or {}
    if event_meta:
        log.debug("SportsEvent %s: %s", url, event_meta)

    return {
        "source_url": url,
        "title": title,
        "team_home": team_home,
        "team_away": team_away,
        "sport": sport,
        "competition": competition,
        "match_date": match_date,
        "author": author,
        "full_text": full_text,
        "published_at": parse_date(raw.get("metaDate")) or match_date,
        "bets": bets,
        "layout": layout,
        "meta": raw.get("meta"),
        "content_html": clean_article_html(content_html),
        "event_meta": event_meta,
    }


async def run_test_parse(urls: Optional[list[tuple[str, str]]] = None) -> None:
    """Тестовый прогон URL из instructions/legalbet.md."""
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
                print(f"  layout:     {data.get('layout')}  (sports_event=schema.org, forecast=классический)")
                print(f"  teams:      {data['team_home']} vs {data['team_away']}")
                print(f"  sport:      {data['sport']} (expected {expected_sport}) {'OK' if ok_sport else 'MISMATCH'}")
                print(f"  competition:{data.get('competition')}")
                print(f"  match_date: {data['match_date']}")
                print(f"  author:     {data.get('author')}")
                print(f"  bets:       {len(data.get('bets') or [])}")
                for b in data.get("bets") or []:
                    print(f"    - {b.get('bet_pick')} @ {b.get('odds')}")
                print(f"  text_len:   {len(data.get('full_text') or '')}")
                if data.get("event_meta"):
                    print(f"  event_meta: {json.dumps(data['event_meta'], ensure_ascii=False)}")
                preview = (data.get("full_text") or "")[:200].replace("\n", " ")
                print(f"  preview:    {preview}...")


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(description="Legalbet parser tests")
    parser.add_argument("--test", action="store_true", help="Parse example URLs from instructions")
    parser.add_argument("--url", action="append", help="Extra URL to test (can repeat)")
    args = parser.parse_args()
    if args.test or args.url:
        extra = [( "", u) for u in (args.url or [])]
        asyncio.run(run_test_parse(_TEST_URLS + extra if args.test else extra))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
