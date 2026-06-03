"""Парсер pontul-zilei.com — разделы ponturi-fotbal / tenis / handbal.

См. instructions/pontul-zilei.md: только матчевые прогнозы (две команды/соперника),
gray_bar, Ponturi recomandate, div.bp-section.ponturile.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import re
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

log = logging.getLogger("pontulzilei")

SOURCE_CONFIG = {
    "name": "pontul-zilei.com",
    "base_url": "https://www.pontul-zilei.com",
    "category_url": "/category/ponturi-pariuri/ponturi-fotbal/",
    "language": "ro",
    "geo": "RO",
}

PONTUL_SECTIONS: list[dict[str, Any]] = [
    {
        "key": "fotbal",
        "path": "/category/ponturi-pariuri/ponturi-fotbal/",
        "sport": "football",
    },
    {
        "key": "tenis",
        "path": "/category/ponturi-pariuri/ponturi-pariuri-tenis/",
        "sport": "tennis",
    },
    {
        "key": "handbal",
        "path": "/category/ponturi-pariuri/ponturi-pariuri/ponturi-handbal/",
        "sport": "handball",
    },
]

_URL_SPORT_HINT: dict[str, str] = {}

_CATEGORY_SPORT = {
    "ponturi fotbal": "football",
    "ponturi handbal": "handball",
    "ponturi pariuri tenis": "tennis",
    "ponturi tenis": "tennis",
}

_TEST_URLS = [
    (
        "football",
        "https://www.pontul-zilei.com/ponturi-pariuri/georgia-vs-romania-ponturi-pariuri-amical-2-iunie-2026/",
    ),
    (
        "handball",
        "https://www.pontul-zilei.com/ponturi-pariuri/gloria-bistrita-si-csm-bucuresti-ataca-semifinalele-ligii-campionilor/",
    ),
    (
        "handball",
        "https://www.pontul-zilei.com/articole-pariuri-sportive/dinamo-bucuresti-veszprem-etapa-3-liga-campionilor-handbal-masculin/",
    ),
    (
        "tennis",
        "https://www.pontul-zilei.com/ponturi-pariuri/mirra-andreeva-vs-sorana-cirstea-ponturi-pariuri-roland-garros-2-iunie-2026/",
    ),
]

_SKIP_SLUG = re.compile(
    r"ponturile-etapei|ponturile-zilei|avancronica|preview|sferturi|biletul|cota-2|"
    r"etapei-\d+|pronosticul-zilei|maine-|pozele-zilei",
    re.I,
)
_MATCH_SLUG = re.compile(
    r"-vs-|_vs_|\bvs\b|-si-|\bsi\b|și|"
    r"dinamo|veszprem|bucuresti|georgia|romania|andreeva",
    re.I,
)
_COTA_RE = re.compile(r"cot[aă]\s+([\d.,]+)", re.I)
_PONT_PICK_RE = re.compile(r"^Pont(?:\s+principal)?\s*:\s*(.+)$", re.I)


_COLLECT_JS = """
() => {
  const skip = /ponturile-etapei|ponturile-zilei|avancronica|preview|sferturi|biletul|cota-2|etapei-\\d+/i;
  const matchSlug = /-vs-|-si-|\\bvs\\b|și|dinamo|veszprem|georgia|romania|andreeva|bistrita/i;
  const out = new Set();
  for (const a of document.querySelectorAll('a[href]')) {
    let href = a.href.split('#')[0].split('?')[0].replace(/\\/$/, '');
    if (!href.includes('pontul-zilei.com')) continue;
    if (skip.test(href)) continue;
    if (href.includes('/ponturipariuri/')) continue;
    if (!href.includes('/ponturi-pariuri/') && !href.includes('/articole-pariuri-sportive/')) continue;
    let path;
    try { path = new URL(href).pathname; } catch (e) { continue; }
    const slug = path.split('/').filter(Boolean).pop() || '';
    if (slug.length < 12 || !matchSlug.test(slug)) continue;
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
  const ogTitle = meta.title || '';

  const barEls = document.querySelectorAll('.gray_bar .bar_element, .b-postat.gray_bar .bar_element');
  let author = '';
  let categoryLinks = [];
  let addedDate = '';
  if (barEls.length >= 3) {
    const tipsterEl = barEls[2];
    const link = tipsterEl.querySelector('a');
    author = (link ? link.textContent : tipsterEl.innerText).trim()
      .replace(/^Tipster:\\s*/i, '').trim();
  }
  if (barEls.length >= 4) {
    for (const a of barEls[3].querySelectorAll('a')) {
      categoryLinks.push({ text: a.textContent.trim(), href: a.href || '' });
    }
  }
  if (barEls.length >= 1) {
    const m = barEls[0].innerText.match(/Adaugat:\\s*(.+)/i);
    if (m) addedDate = m[1].trim();
  }

  const breadcrumbs = [];
  const crumbRoot = document.querySelector('.breadcrumbs, .breadcrumb');
  if (crumbRoot) {
    for (const a of crumbRoot.querySelectorAll('a')) {
      const text = a.textContent?.trim();
      if (text) breadcrumbs.push({ text, href: a.href || '' });
    }
    breadcrumbs.push({ text: crumbRoot.innerText.replace(/\\s+/g, ' ').trim(), href: '' });
  }

  let contentHtml = '';
  const contentRoot = document.querySelector('.bp-section.ponturile, .ponturile.bp-section');
  if (contentRoot) {
    const clone = contentRoot.cloneNode(true);
    clone.querySelectorAll('img, script, style, iframe').forEach((el) => el.remove());
    contentHtml = clone.innerHTML;
  }

  const bets = [];
  const betSeen = new Set();

  function addBet(raw) {
    const line = (raw || '').trim();
    if (!line || line.length < 4 || betSeen.has(line)) return;
    betSeen.add(line);
    let odds = '';
    const om = line.match(/cot[aă]\\s+([\\d.,]+)/i);
    if (om) odds = om[1];
    let pick = line.replace(/^Pont(?:\\s+principal)?\\s*:\\s*/i, '').trim();
    pick = pick.replace(/,?\\s*cot[aă]\\s+[\\d.,]+.*$/i, '').trim();
    bets.push({ bet_type: '1X2', bet_pick: pick || line, odds, is_main: bets.length === 0, raw: line });
  }

  if (contentRoot) {
    for (const h of contentRoot.querySelectorAll('h2, h3, h4, strong, p')) {
      if (!/ponturi\\s+recomandate/i.test(h.textContent || '')) continue;
      let el = h.nextElementSibling;
      for (let i = 0; i < 8 && el; i++, el = el.nextElementSibling) {
        if (el.matches('ul, ol')) {
          for (const li of el.querySelectorAll('li')) addBet(li.innerText);
          break;
        }
      }
    }
    for (const span of contentRoot.querySelectorAll('span[style]')) {
      const st = (span.getAttribute('style') || '').toLowerCase();
      if (!st.includes('#ff0000') && !st.includes('ff0000')) continue;
      const t = span.innerText?.trim() || '';
      if (/pont/i.test(t)) addBet(t);
    }
  }

  const redLines = bets.map((b) => b.raw);

  return {
    h1,
    ogTitle,
    meta,
    metaDate: addedDate,
    author,
    categoryLinks,
    breadcrumbs,
    content_html: contentHtml,
    bets,
    redLines,
  };
}
"""


def _is_valid_collect_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    if "/ponturipariuri/" in path:
        return False
    if "/ponturi-pariuri/" not in path and "/articole-pariuri-sportive/" not in path:
        return False
    if _SKIP_SLUG.search(path):
        return False
    slug = path.rstrip("/").split("/")[-1]
    if len(slug) < 12:
        return False
    return bool(_MATCH_SLUG.search(slug))


def _sport_from_categories(raw: dict) -> Optional[str]:
    for link in raw.get("categoryLinks") or []:
        if not isinstance(link, dict):
            continue
        key = link.get("text", "").strip().lower()
        if key in _CATEGORY_SPORT:
            return _CATEGORY_SPORT[key]
        if "fotbal" in key:
            return "football"
        if "handbal" in key:
            return "handball"
        if "tenis" in key:
            return "tennis"
    return None


def _infer_sport_from_url(url: str) -> Optional[str]:
    path = urlparse(url).path.lower()
    if "handbal" in path or "veszprem" in path or "bistrita" in path:
        return "handball"
    if "tenis" in path or "roland-garros" in path or "andreeva" in path:
        return "tennis"
    if "fotbal" in path or "amical" in path or "georgia" in path:
        return "football"
    return None


def _competition_from_h1(h1: str) -> str:
    text = h1.strip()
    for sep in (" – ", " — ", " - "):
        if sep in text:
            tail = text.split(sep, 1)[1].strip()
            tail = re.sub(r"^Ponturi\s+pariuri\s+", "", tail, flags=re.I)
            return tail
    return ""


def _extract_match_day_text(h1: str, breadcrumbs_text: str, url: str) -> str:
    for src in (h1, breadcrumbs_text, url):
        m = re.search(
            r"(\d{1,2})\s+(ianuarie|februarie|martie|aprilie|mai|iunie|iulie|august|"
            r"septembrie|octombrie|noiembrie|decembrie)\s+(\d{4})",
            src,
            re.I,
        )
        if m:
            return f"{m.group(1)} {m.group(2)} {m.group(3)}"
    return ""


def _extract_kickoff_time(text: str) -> str:
    if not text:
        return ""
    for pat in (
        r"ora\s+(\d{1,2}:\d{2})",
        r"de la ora\s+(\d{1,2}:\d{2})",
        r"(\d{1,2}:\d{2})\s*-\s*(?:Digi|Eurosport|Prima|Max)",
    ):
        m = re.search(pat, text[:6000], re.I)
        if m:
            return m.group(1)
    return ""


def _build_kickoff_text(raw: dict, full_text: str, url: str) -> str:
    h1 = raw.get("h1") or ""
    crumb_tail = ""
    for c in raw.get("breadcrumbs") or []:
        if isinstance(c, dict) and c.get("text") and "Ponturi" not in c.get("text", ""):
            crumb_tail = c.get("text", "")
    day = _extract_match_day_text(h1, crumb_tail, url)
    time_part = _extract_kickoff_time(full_text)
    if day and time_part:
        return f"{day} {time_part}"
    return day


def _teams_from_pick_lines(lines: list[str]) -> tuple[str, str]:
    for line in lines:
        m = re.search(
            r"(?:Pont\s+)?([A-Za-zÀ-ÿ0-9 .'()‑-]{2,50}?)\s+vs\s+"
            r"([A-Za-zÀ-ÿ0-9 .'()‑-]{2,50}?)\s*[:\-]",
            line,
            re.I,
        )
        if m:
            return m.group(1).strip(), m.group(2).strip()
    return "", ""


def _resolve_teams(raw: dict, url: str) -> tuple[str, str]:
    h1 = raw.get("h1") or ""
    og = raw.get("ogTitle") or ""
    picks = [b.get("raw") or b.get("bet_pick") or "" for b in raw.get("bets") or []]

    for title in (h1, og):
        home, away = parse_teams_from_title(title)
        if home and away:
            return home, away

    home, away = _teams_from_pick_lines(picks)
    if home and away:
        return home, away

    slug = urlparse(url).path.rstrip("/").split("/")[-1]
    m = re.search(r"^([a-z0-9-]+)-vs-([a-z0-9-]+)-", slug, re.I)
    if m:
        return m.group(1).replace("-", " ").title(), m.group(2).replace("-", " ").title()

    m = re.search(r"^([a-z0-9-]+)-([a-z0-9-]+)-etapa", slug, re.I)
    if m:
        return m.group(1).replace("-", " ").title(), m.group(2).replace("-", " ").title()

    return "", ""


def _is_valid_teams(home: str, away: str) -> bool:
    if not home or not away or len(home) < 2 or len(away) < 2:
        return False
    junk = re.compile(r"^ponturi$|^cote$|^pariuri$", re.I)
    return not (junk.search(home) or junk.search(away))


def _build_match_date(raw: dict, full_text: str, url: str) -> Optional[datetime]:
    geo = SOURCE_CONFIG.get("geo")
    kickoff = _build_kickoff_text(raw, full_text, url)
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
        raw_line = (b.get("raw") or b.get("bet_pick") or "").strip()
        pick = (b.get("bet_pick") or "").strip()
        if raw_line:
            m = _PONT_PICK_RE.match(raw_line)
            if m:
                pick = m.group(1).strip()
            pick = _COTA_RE.sub("", pick).strip(" ,-")
        odds = parse_odds(b.get("odds"))
        if not odds and raw_line:
            om = _COTA_RE.search(raw_line)
            if om:
                odds = parse_odds(om.group(1))
        key = (pick, str(odds) if odds else "")
        if key in seen or (not pick and not odds):
            continue
        seen.add(key)
        out.append(
            {
                "bet_type": b.get("bet_type") or "1X2",
                "bet_pick": pick or raw_line,
                "odds": odds,
                "is_main": b.get("is_main", len(out) == 0),
            }
        )
    return out


async def get_article_urls(page: Any) -> list[str]:
    from src.scraper.utils.browser import wait_cloudflare

    global _URL_SPORT_HINT
    _URL_SPORT_HINT = {}
    base = SOURCE_CONFIG["base_url"].rstrip("/")
    found: set[str] = set()

    for section in PONTUL_SECTIONS:
        url = base + section["path"]
        log.info("Collect URLs: %s (%s)", section["key"], url)
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await wait_cloudflare(page)
        urls = await page.evaluate(_COLLECT_JS)
        for u in urls:
            u = u.split("#")[0].split("?")[0].rstrip("/")
            if not _is_valid_collect_url(u):
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

    content_html = raw.get("content_html") or ""
    full_text = html_to_plain_text(clean_article_html(content_html))

    match_date = _build_match_date(raw, full_text, url)
    if not match_date:
        log.warning("Skip %s: no match_date", url)
        return None

    sport = (
        _infer_sport_from_url(url)
        or _URL_SPORT_HINT.get(url.rstrip("/"))
        or _sport_from_categories(raw)
    )
    if not sport:
        log.warning("Skip %s: could not resolve sport", url)
        return None

    bets = _parse_bets(raw.get("bets"))
    competition = _competition_from_h1(title)

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
                print(
                    f"  sport:      {data['sport']} (expected {expected_sport}) "
                    f"{'OK' if ok_sport else 'MISMATCH'}"
                )
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
    parser = argparse.ArgumentParser(description="Pontul-zilei parser tests")
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
