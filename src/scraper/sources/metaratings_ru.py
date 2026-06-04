"""Парсер metaratings.ru — разделы /prognozy/{sport}/.

См. instructions/metaratings_ru.md: SportsEvent (JSON-LD), PostAuthor, workarea-text, versus-info.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import re
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urlparse

from src.scraper.utils.html_clean import clean_article_html, html_to_plain_text
from src.scraper.utils.match_datetime import parse_schema_start_date, to_storage_datetime
from src.scraper.utils.normalizer import (
    default_kickoff_storage,
    normalize_sport,
    parse_date,
    parse_date_from_url,
    parse_match_datetime,
    parse_odds,
)
from src.scraper.utils.teams import parse_teams_from_title, sanitize_team_label

log = logging.getLogger("metaratings_ru")

SOURCE_CONFIG = {
    "name": "metaratings.ru",
    "base_url": "https://metaratings.ru",
    "category_url": "/prognozy/futbol/",
    "language": "ru",
    "geo": "RU",
}

METARATINGS_SECTIONS: list[dict[str, Any]] = [
    {"key": "futbol", "path": "/prognozy/futbol/", "sport": "football"},
    {"key": "hokkey", "path": "/prognozy/hokkey/", "sport": "hockey"},
    {"key": "tennis", "path": "/prognozy/tennis/", "sport": "tennis"},
    {"key": "basketbol", "path": "/prognozy/basketbol/", "sport": "basketball"},
    {"key": "voleybol", "path": "/prognozy/voleybol/", "sport": "volleyball"},
]

_URL_SPORT_HINT: dict[str, str] = {}

_SKIP_URL = re.compile(
    r"/prognozy/(?:futbol|hokkey|tennis|basketbol|voleybol)/?$"
    r"|bilet|sbornaya|luchshie-prognoz|top-prognoz|reyting|/news/",
    re.I,
)

_TEST_URLS = [
    (
        "football",
        "https://metaratings.ru/prognozy/futbol/sloveniya-kipr-prognoz-i-stavki-na-tovarisheskii-match-4-iyunya-2026-goda/",
    ),
    (
        "tennis",
        "https://metaratings.ru/prognozy/tennis/shnaider-khvalinska-prognoz-i-stavki-na-match-rolan-garros-4-iyunya-2026-goda/",
    ),
    (
        "basketball",
        "https://metaratings.ru/prognozy/basketbol/cska-uniks-prognoz-na-match-edinoi-ligi-vtb-4-iyunya-2026-goda/",
    ),
]

_COLLECT_JS = """
() => {
  const skipSection = /\\/prognozy\\/(futbol|hokkey|tennis|basketbol|voleybol)\\/?$/i;
  const skipHref = /bilet|sbornaya|luchshie|top-prognoz|reyting|\\/news\\//i;
  const dateSlug = /\\d{1,2}-(?:iyunya|iyulya|avgusta|sentyabrya|oktyabrya|noyabrya|dekabrya|yanvarya|fevralya|marta|aprelya|maya)-\\d{4}|\\d{2}-\\d{2}-\\d{4}/i;
  const out = new Set();
  for (const a of document.querySelectorAll('a[href]')) {
    let href = a.href.split('#')[0].split('?')[0].replace(/\\/$/, '');
    if (!href.includes('metaratings.ru')) continue;
    if (skipSection.test(href) || skipHref.test(href)) continue;
    if (!href.includes('/prognozy/')) continue;
    let path;
    try { path = new URL(href).pathname; } catch (e) { continue; }
    const parts = path.split('/').filter(Boolean);
    if (parts.length < 3) continue;
    const slug = parts[parts.length - 1];
    if (slug.length < 25 || !/prognoz/i.test(slug)) continue;
    if (!dateSlug.test(slug)) continue;
    out.add(href);
  }
  return [...out];
}
"""

_PARSE_JS = """
() => {
  const getMeta = (sel) => document.querySelector(sel)?.getAttribute('content')?.trim() || '';

  const findSportsEvent = (obj) => {
    if (!obj) return null;
    if (Array.isArray(obj)) {
      for (const item of obj) {
        const found = findSportsEvent(item);
        if (found) return found;
      }
      return null;
    }
    const t = obj['@type'];
    if (t === 'SportsEvent' || (Array.isArray(t) && t.includes('SportsEvent'))) return obj;
    if (obj['@graph']) return findSportsEvent(obj['@graph']);
    return null;
  };

  const teamName = (t) => {
    if (!t) return '';
    if (typeof t === 'string') return t.trim();
    return (t.name || '').trim();
  };

  let event = null;
  for (const script of document.querySelectorAll('script[type="application/ld+json"]')) {
    try {
      const data = JSON.parse(script.textContent || '');
      event = findSportsEvent(data);
      if (event) break;
    } catch (e) {}
  }

  let team_home = '';
  let team_away = '';
  let kickoff = '';
  let sport = '';
  let competition = '';

  if (event) {
    kickoff = event.startDate || '';
    sport = event.sport || '';
    team_home = teamName(event.homeTeam);
    team_away = teamName(event.awayTeam);
    if (!team_home && Array.isArray(event.competitor) && event.competitor.length >= 2) {
      team_home = teamName(event.competitor[0]);
      team_away = teamName(event.competitor[1]);
    }
  }

  if (!kickoff) {
    kickoff = getMeta('meta[itemprop="startDate"]')
      || document.querySelector('[itemprop="startDate"]')?.getAttribute('content') || '';
  }
  if (!sport) sport = getMeta('meta[itemprop="sport"]') || '';
  if (!team_home) {
    team_home = document.querySelector('[itemprop="homeTeam"] meta[itemprop="name"]')?.getAttribute('content')
      || document.querySelector('[itemprop="homeTeam"]')?.textContent?.trim() || '';
  }
  if (!team_away) {
    team_away = document.querySelector('[itemprop="awayTeam"] meta[itemprop="name"]')?.getAttribute('content')
      || document.querySelector('[itemprop="awayTeam"]')?.textContent?.trim() || '';
  }

  const h1 = document.querySelector('h1')?.innerText?.trim() || '';
  const meta = {
    title: getMeta('meta[property="og:title"]') || document.title || '',
    description: getMeta('meta[property="og:description"]') || getMeta('meta[name="description"]'),
  };

  let author = '';
  const authorEl = document.querySelector('.PostAuthor, [class*="PostAuthor"]');
  if (authorEl) {
    const link = authorEl.querySelector('a');
    author = (link ? link.textContent : authorEl.textContent || '').trim();
    author = author.replace(/^Эксперт:?\\s*/i, '').trim();
  }

  const versusEl = document.querySelector('.versus-info.workarea-text, .versus-info');
  const versusText = versusEl?.innerText?.trim().replace(/\\s+/g, ' ') || '';

  const contentParts = [];
  for (const block of document.querySelectorAll('.workarea-text')) {
    if (block.closest('.versus-info')) continue;
    const clone = block.cloneNode(true);
    clone.querySelectorAll('script, style, iframe').forEach((el) => el.remove());
    const html = clone.innerHTML?.trim();
    if (html) contentParts.push(html);
  }
  const content_html = contentParts.join('\\n');

  const betLines = [];
  for (const block of document.querySelectorAll('.workarea-text')) {
    for (const el of block.querySelectorAll('p, li, strong')) {
      const t = (el.innerText || '').trim().replace(/\\s+/g, ' ');
      if (/^(Прогноз|Ставка)\\s*[—–-]/i.test(t)) betLines.push(t);
    }
  }

  return {
    h1,
    meta,
    author,
    versusText,
    team_home,
    team_away,
    kickoff,
    sport,
    competition,
    content_html,
    betLines,
    event,
  };
}
"""

_PATH_SPORT = [
    (re.compile(r"/prognozy/tennis/", re.I), "tennis"),
    (re.compile(r"/prognozy/hokkey/", re.I), "hockey"),
    (re.compile(r"/prognozy/basketbol/", re.I), "basketball"),
    (re.compile(r"/prognozy/voleybol/", re.I), "volleyball"),
    (re.compile(r"/prognozy/futbol/", re.I), "football"),
]

_BET_LINE = re.compile(
    r"^(?:Прогноз|Ставка)\s*[—–-]\s*(.+?)\s+с\s+коэффициентом\s+([\d.,]+)",
    re.I,
)


def _sport_from_url(url: str) -> str:
    for pat, sport in _PATH_SPORT:
        if pat.search(url):
            return sport
    return ""


def _is_valid_article_url(url: str) -> bool:
    if _SKIP_URL.search(url):
        return False
    path = urlparse(url).path
    parts = [p for p in path.split("/") if p]
    if len(parts) < 3:
        return False
    slug = parts[-1].lower()
    if len(slug) < 25 or "prognoz" not in slug:
        return False
    if not re.search(
        r"\d{1,2}-(?:iyunya|iyulya|avgusta|sentyabrya|oktyabrya|noyabrya|dekabrya|"
        r"yanvarya|fevralya|marta|aprelya|maya)-\d{4}|\d{2}-\d{2}-\d{4}",
        slug,
    ):
        return False
    return True


def _is_valid_teams(team_home: str, team_away: str) -> bool:
    if not team_home or not team_away or len(team_home) > 80 or len(team_away) > 80:
        return False
    bad = re.compile(r"прогноз|ставк|metaratings|букмекер", re.I)
    return not bad.search(team_home) and not bad.search(team_away)


def _competition_from_versus(text: str) -> tuple[str, str]:
    if not text:
        return "", ""
    parts = [p.strip() for p in re.split(r"\s*\.\s*", text) if p.strip()]
    if len(parts) >= 2:
        sport = normalize_sport(parts[0]) or ""
        comp = ". ".join(parts[1:])
        return sport, comp
    return "", text.strip()


def _teams_from_slug(url: str) -> tuple[str, str]:
    slug = urlparse(url).path.rstrip("/").split("/")[-1].lower()
    head = re.split(r"-prognoz", slug, maxsplit=1)[0]
    head = head.split("-na-match-")[0].split("-na-tovarisheskii-")[0]
    parts = [p for p in head.split("-") if p]
    if len(parts) >= 2:
        mid = len(parts) // 2
        home = " ".join(parts[:mid]).title()
        away = " ".join(parts[mid:]).title()
        return home, away
    return "", ""


def _resolve_teams(raw: dict, url: str) -> tuple[str, str]:
    candidates: list[tuple[str, str]] = []

    rh = (raw.get("team_home") or "").strip()
    ra = (raw.get("team_away") or "").strip()
    if rh or ra:
        candidates.append((rh, ra))

    meta_title = (raw.get("meta") or {}).get("title") or ""
    for title in (raw.get("h1") or "", meta_title):
        if title:
            th, ta = parse_teams_from_title(title)
            if th or ta:
                candidates.append((th, ta))

    candidates.append(_teams_from_slug(url))

    for home, away in candidates:
        home = sanitize_team_label(home)
        away = sanitize_team_label(away)
        if _is_valid_teams(home, away):
            return home, away
    return "", ""


def _build_match_date(raw: dict, url: str) -> Optional[datetime]:
    geo = SOURCE_CONFIG.get("geo")
    kickoff = (raw.get("kickoff") or "").strip()
    if kickoff:
        dt = parse_schema_start_date(kickoff, geo=geo)
        if dt:
            return dt
        dt = parse_match_datetime(kickoff, url=url, geo=geo)
        if dt:
            return dt
    dt = parse_match_datetime(raw.get("h1") or "", url=url, geo=geo)
    if dt:
        return dt
    d = parse_date_from_url(url, geo=geo)
    return default_kickoff_storage(d, geo=geo) if d else None


def _parse_bets(bet_lines: list[str], full_text: str) -> list[dict]:
    lines = list(bet_lines or [])
    if not lines and full_text:
        for line in full_text.splitlines():
            line = line.strip()
            if _BET_LINE.match(line):
                lines.append(line)

    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for line in lines:
        m = _BET_LINE.match(line.strip())
        if not m:
            continue
        pick = re.sub(r"\s+в\s+БК\s+.+$", "", m.group(1).strip(), flags=re.I)
        pick = re.sub(r"\s+", " ", pick).strip(" ,-")
        odds = parse_odds(m.group(2))
        if not pick or odds is None:
            continue
        key = (pick, str(odds))
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "bet_type": "1X2",
                "bet_pick": pick,
                "odds": odds,
                "is_main": len(out) == 0,
            }
        )
    return out


def _resolve_sport(raw: dict, url: str) -> str:
    versus_sport, _ = _competition_from_versus(raw.get("versusText") or "")
    for candidate in (
        normalize_sport(raw.get("sport") or ""),
        versus_sport,
        _URL_SPORT_HINT.get(url.rstrip("/")),
        _sport_from_url(url),
    ):
        if candidate:
            return candidate
    return ""


async def get_article_urls(page: Any) -> list[str]:
    from src.scraper.utils.browser import wait_cloudflare

    global _URL_SPORT_HINT
    _URL_SPORT_HINT = {}
    base = SOURCE_CONFIG["base_url"].rstrip("/")
    found: set[str] = set()

    for section in METARATINGS_SECTIONS:
        url = base + section["path"]
        log.info("Collect URLs: %s (%s)", section["key"], url)
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await wait_cloudflare(page)
        urls = await page.evaluate(_COLLECT_JS)
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

    team_home, team_away = _resolve_teams(raw, url)
    if not _is_valid_teams(team_home, team_away):
        log.warning("Skip %s: invalid teams %r vs %r", url, team_home, team_away)
        return None

    match_date = _build_match_date(raw, url)
    if not match_date:
        log.warning("Skip %s: no match_date", url)
        return None

    content_html = raw.get("content_html") or ""
    full_text = html_to_plain_text(clean_article_html(content_html))

    sport = _resolve_sport(raw, url)
    if not sport:
        log.warning("Skip %s: could not resolve sport", url)
        return None

    _, competition = _competition_from_versus(raw.get("versusText") or "")
    if not competition:
        competition = (raw.get("competition") or "").strip()

    bets = _parse_bets(raw.get("betLines") or [], full_text)
    if not bets:
        log.info("Skip %s: no bets with odds", url)
        return None

    author = (raw.get("author") or "").strip()

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
        "published_at": match_date,
        "bets": bets,
        "meta": raw.get("meta"),
        "content_html": clean_article_html(content_html),
        "event_meta": raw.get("event") or {},
    }


async def run_test_parse(urls: Optional[list[tuple[str, str]]] = None) -> None:
    from src.scraper.utils.browser import (
        browser_lifecycle,
        page_session,
        scrape_geo_context,
    )

    pairs = urls or _TEST_URLS
    verify = SOURCE_CONFIG["base_url"].rstrip("/") + SOURCE_CONFIG["category_url"]
    geo = SOURCE_CONFIG.get("geo")
    async with browser_lifecycle():
        async with scrape_geo_context(geo):
            async with page_session(verify_url=verify) as (page, _proxy):
                for expected_sport, url in pairs:
                    print(f"\n{'=' * 60}\n{url}\n")
                    data = await parse_prediction(page, url)
                    if not data:
                        print("  SKIP/FAIL")
                        continue
                    ok = data["sport"] == expected_sport
                    print(f"  teams:      {data['team_home']} vs {data['team_away']}")
                    print(
                        f"  sport:      {data['sport']} (expected {expected_sport}) "
                        f"{'OK' if ok else 'MISMATCH'}"
                    )
                    print(f"  competition:{data.get('competition')}")
                    print(f"  match_date: {data['match_date']}")
                    print(f"  author:     {data.get('author')}")
                    print(f"  bets:       {len(data.get('bets') or [])}")
                    for b in data.get("bets") or []:
                        print(f"    - {b.get('bet_pick')} @ {b.get('odds')}")


def main() -> None:
    from src.config import setup_logging

    setup_logging()
    parser = argparse.ArgumentParser(description="Metaratings.ru parser tests")
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--url", action="append")
    args = parser.parse_args()
    if args.test or args.url:
        extra = [("", u) for u in (args.url or [])]
        asyncio.run(run_test_parse(_TEST_URLS + extra if args.test else extra))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
