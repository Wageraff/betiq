"""Парсер betonmobile.ru — разделы /prognozy/prognozy-na-{sport}/.

См. instructions/betonmobile_ru.md: s_p_n_h_b_title, s_p_n_h_b_liga, дата/время,
s_p_n_a_b_name, text-block / s_p_n_s_box, s_p_n_stavka_t / s_p_n_stavka_k.
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
from src.scraper.utils.match_datetime import parse_schema_start_date
from src.scraper.utils.normalizer import (
    default_kickoff_storage,
    normalize_sport,
    parse_date_from_url,
    parse_match_datetime,
    parse_odds,
)
from src.scraper.utils.teams import parse_teams_from_title, sanitize_team_label

log = logging.getLogger("betonmobile_ru")

SOURCE_CONFIG = {
    "name": "betonmobile.ru",
    "base_url": "https://betonmobile.ru",
    "category_url": "/prognozy/prognozy-na-futbol",
    "language": "ru",
    "geo": "RU",
}

BETON_SECTIONS: list[dict[str, Any]] = [
    {"key": "football", "path": "/prognozy/prognozy-na-futbol", "sport": "football"},
    {"key": "hockey", "path": "/prognozy/prognozy-na-hokkej", "sport": "hockey"},
    {"key": "tennis", "path": "/prognozy/prognozy-na-tennis", "sport": "tennis"},
    {"key": "basketball", "path": "/prognozy/prognozy-na-basketbol", "sport": "basketball"},
]

_URL_SPORT_HINT: dict[str, str] = {}

_SKIP_PATH = re.compile(
    r"/prognozy(?:/|$)|/page/|/tag/|/author/|/search|wp-json|/bonusy|/bukmekery",
    re.I,
)

_DATE_SLUG = re.compile(
    r"\d{1,2}-(?:iyunya|iyulya|avgusta|sentyabrya|oktyabrya|noyabrya|dekabrya|"
    r"yanvarya|fevralya|marta|aprelya|maya)-\d{4}|\d{2}-\d{2}-\d{4}",
    re.I,
)

_TEST_URLS = [
    (
        "football",
        "https://betonmobile.ru/moldova-bolgariya-5-iyunya-2026-sumeyut-li-moldavane-pokazat-harakter",
    ),
    (
        "hockey",
        "https://betonmobile.ru/karolina-harrikeynz-vegas-golden-nayts-5-iyunya-2026-kto-zaberet-vtoroy-match",
    ),
]

_COLLECT_JS = """
() => {
  const skip = /\\/prognozy\\/prognozy-na-|\\/page\\/|\\?page=|wp-json|\\/tag\\//i;
  const dateSlug = /\\d{1,2}-(?:iyunya|iyulya|avgusta|sentyabrya|oktyabrya|noyabrya|dekabrya|yanvarya|fevralya|marta|aprelya|maya)-\\d{4}|\\d{2}-\\d{2}-\\d{4}/i;
  const out = new Set();
  for (const a of document.querySelectorAll('a[href]')) {
    let href = a.href.split('#')[0].split('?')[0].replace(/\\/$/, '');
    if (!href.includes('betonmobile.ru')) continue;
    if (skip.test(href)) continue;
    let path;
    try { path = new URL(href).pathname; } catch (e) { continue; }
    const parts = path.split('/').filter(Boolean);
    if (parts.length !== 1) continue;
    const slug = parts[0];
    if (slug.length < 18 || !dateSlug.test(slug)) continue;
    out.add(href);
  }
  return [...out];
}
"""

_PARSE_JS = """
() => {
  const getMeta = (sel) => document.querySelector(sel)?.getAttribute('content')?.trim() || '';

  const teamsEl = document.querySelector('.s_p_n_h_b_title');
  const teamsText = (teamsEl?.innerText || '').trim().replace(/\\s+/g, ' ');

  const competition = (document.querySelector('.s_p_n_h_b_liga')?.innerText || '')
    .trim().replace(/\\s+/g, ' ');
  const matchDateText = (document.querySelector('.s_p_n_h_b_i_date')?.innerText || '')
    .trim().replace(/\\s+/g, ' ');
  const matchTimeText = (document.querySelector('.s_p_n_h_b_i_time')?.innerText || '')
    .trim().replace(/\\s+/g, ' ');
  const author = (document.querySelector('.s_p_n_a_b_name')?.innerText || '')
    .trim().replace(/\\s+/g, ' ');

  const h1 = document.querySelector('h1')?.innerText?.trim()
    || teamsText
    || getMeta('meta[property="og:title"]')
    || '';

  const meta = {
    title: getMeta('meta[property="og:title"]') || document.title || '',
    description: getMeta('meta[property="og:description"]') || getMeta('meta[name="description"]'),
  };

  const stripNoise = (root) => {
    const clone = root.cloneNode(true);
    clone.querySelectorAll(
      'script, style, iframe, nav, footer, .s_p_n_stavka_t, .s_p_n_stavka_k, [class*="stavka"]'
    ).forEach((el) => el.remove());
    return clone;
  };

  const textParts = [];
  const textSel = [
    '.text-block.single-text.s_p_n_c_block.br8',
    '.text-block.s_p_n_c_block',
    '.s_p_n_s_box.br8',
    '.s_p_n_s_box',
    '.s_p_n_c_block',
  ];
  const seenText = new Set();
  for (const sel of textSel) {
    document.querySelectorAll(sel).forEach((el) => {
      const t = stripNoise(el).innerText?.trim().replace(/\\s+/g, ' ');
      if (t && t.length > 40 && !seenText.has(t)) {
        seenText.add(t);
        textParts.push(t);
      }
    });
  }
  const domText = textParts.join('\\n\\n').trim();

  let content_html = '';
  const htmlParts = [];
  for (const sel of textSel) {
    document.querySelectorAll(sel).forEach((el) => {
      const html = stripNoise(el).innerHTML?.trim();
      if (html && html.length > 60) htmlParts.push(html);
    });
  }
  if (htmlParts.length) {
    content_html = [...new Set(htmlParts)].join('\\n');
  }

  const betsDom = [];
  const seenBet = new Set();
  const pushBet = (pick, odds) => {
    pick = (pick || '').trim().replace(/\\s+/g, ' ');
    odds = (odds || '').trim();
    const om = odds.match(/(\\d{1,2}[.,]\\d{2})/);
    if (!pick || !om || pick.length > 100 || pick.length < 3) return;
    odds = om[1];
    const key = pick + '|' + odds;
    if (seenBet.has(key)) return;
    seenBet.add(key);
    betsDom.push({ pick, odds });
  };

  document.querySelectorAll('.s_p_n_stavka_t').forEach((pickEl) => {
    const row = pickEl.closest('[class*="stavka"]') || pickEl.parentElement;
    const coeffEl = row?.querySelector('.s_p_n_stavka_k')
      || pickEl.parentElement?.querySelector('.s_p_n_stavka_k')
      || pickEl.nextElementSibling;
    pushBet(pickEl.textContent, coeffEl ? coeffEl.textContent : '');
  });

  const datePublished = getMeta('meta[property="article:published_time"]')
    || document.querySelector('time[datetime]')?.getAttribute('datetime')
    || '';

  return {
    h1,
    meta,
    teamsText,
    competition,
    matchDateText,
    matchTimeText,
    author,
    domText,
    content_html,
    betsDom,
    datePublished,
  };
}
"""

_PATH_SPORT = [
    (re.compile(r"prognozy-na-tennis|tennis", re.I), "tennis"),
    (re.compile(r"prognozy-na-hokkej|hokkej|hockey", re.I), "hockey"),
    (re.compile(r"prognozy-na-basketbol|basketbol", re.I), "basketball"),
    (re.compile(r"prognozy-na-futbol|futbol|football", re.I), "football"),
]


def _sport_from_url(url: str) -> str:
    for pat, sport in _PATH_SPORT:
        if pat.search(url):
            return sport
    return _URL_SPORT_HINT.get(url.rstrip("/"), "")


def _is_valid_article_url(url: str) -> bool:
    if _SKIP_PATH.search(urlparse(url).path):
        return False
    parts = [p for p in urlparse(url).path.split("/") if p]
    if len(parts) != 1:
        return False
    return bool(_DATE_SLUG.search(parts[0]))


def _is_valid_teams(team_home: str, team_away: str) -> bool:
    if not team_home or not team_away or len(team_home) > 80 or len(team_away) > 80:
        return False
    bad = re.compile(r"прогноз|ставк|betonmobile|букмекер", re.I)
    return not bad.search(team_home) and not bad.search(team_away)


def _clean_team_display(name: str) -> str:
    name = sanitize_team_label((name or "").strip())
    return name.strip(" «»\"'")


def _resolve_teams(raw: dict, url: str) -> tuple[str, str]:
    candidates: list[tuple[str, str]] = []

    teams_text = (raw.get("teamsText") or "").strip()
    if teams_text:
        th, ta = parse_teams_from_title(teams_text)
        if th and ta:
            candidates.append((th, ta))

    for title in (raw.get("h1") or "", (raw.get("meta") or {}).get("title") or ""):
        if title:
            th, ta = parse_teams_from_title(title)
            if th and ta:
                candidates.append((th, ta))

    for home, away in candidates:
        home = _clean_team_display(home)
        away = _clean_team_display(away)
        if _is_valid_teams(home, away):
            return home, away
    return "", ""


def _build_match_date(raw: dict, url: str) -> Optional[datetime]:
    geo = SOURCE_CONFIG.get("geo")
    date_txt = (raw.get("matchDateText") or "").strip()
    time_txt = (raw.get("matchTimeText") or "").strip()
    combined = " ".join(p for p in (date_txt, time_txt) if p)
    if combined:
        dt = parse_match_datetime(combined, url=url, geo=geo)
        if dt:
            return dt
    for src in (raw.get("h1") or "", combined):
        dt = parse_match_datetime(src, url=url, geo=geo)
        if dt:
            return dt
    d = parse_date_from_url(url, geo=geo)
    return default_kickoff_storage(d, geo=geo) if d else None


def _clean_bet_pick(pick: str) -> str:
    pick = (pick or "").strip()
    pick = re.sub(r"\s+", " ", pick)
    pick = pick.strip(" ,-«»\"'")
    if len(pick) < 3 or len(pick) > 100:
        return ""
    if re.search(r"^(?:коэффициент|ставка|букмекер|прогноз)\b", pick, re.I):
        return ""
    return pick


def _bet_pick_key(pick: str, odds: str) -> str:
    p = pick.lower()
    p = re.sub(r"[«»\"'–—]", "", p)
    p = re.sub(r"\s+", " ", p).strip()
    return f"{p}|{odds}"


def _dedupe_bets(bets: list[dict]) -> list[dict]:
    kept: list[dict] = []
    keys: list[str] = []
    for b in bets:
        key = _bet_pick_key(b["bet_pick"], str(b["odds"]))
        if key in keys:
            idx = keys.index(key)
            if len(b["bet_pick"]) > len(kept[idx]["bet_pick"]):
                kept[idx] = b
            continue
        keys.append(key)
        kept.append(b)
    for i, b in enumerate(kept):
        b["is_main"] = i == 0
    return kept


def _parse_bets(bets_dom: list[dict]) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()

    for item in bets_dom or []:
        pick = _clean_bet_pick(item.get("pick") or "")
        odds = parse_odds(item.get("odds") or "")
        if not pick or odds is None:
            continue
        key = _bet_pick_key(pick, str(odds))
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

    return _dedupe_bets(out)


def _resolve_sport(raw: dict, url: str) -> str:
    competition = (raw.get("competition") or "").strip()
    body = " ".join(
        [
            competition,
            raw.get("h1") or "",
            (raw.get("domText") or "")[:2000],
        ]
    )
    for candidate in (
        _sport_from_url(url),
        _URL_SPORT_HINT.get(url.rstrip("/")),
        normalize_sport(competition),
    ):
        if candidate:
            return candidate
    slug = urlparse(url).path.lower()
    if re.search(r"hokkej|nhl|хоккей", slug + body, re.I):
        return "hockey"
    if re.search(r"tennis|теннис|atp|wta|garros", slug + body, re.I):
        return "tennis"
    if re.search(r"basket|баскет|vtb", slug + body, re.I):
        return "basketball"
    if re.search(r"futbol|футбол|сборн", slug + body, re.I):
        return "football"
    return ""


async def get_article_urls(page: Any) -> list[str]:
    from src.scraper.utils.browser import wait_cloudflare

    global _URL_SPORT_HINT
    _URL_SPORT_HINT = {}
    base = SOURCE_CONFIG["base_url"].rstrip("/")
    found: set[str] = set()

    for section in BETON_SECTIONS:
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
    try:
        await page.wait_for_selector(
            ".s_p_n_h_b_title, .s_p_n_stavka_t",
            timeout=20_000,
            state="attached",
        )
    except Exception:
        pass

    raw = await page.evaluate(_PARSE_JS) or {}
    title = (raw.get("h1") or "").strip()
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

    dom_text = (raw.get("domText") or "").strip()
    content_html = raw.get("content_html") or ""
    if dom_text:
        full_text = dom_text
        text_source = "text-block"
    elif content_html:
        full_text = html_to_plain_text(content_html) or html_to_plain_text(
            clean_article_html(content_html)
        )
        text_source = "text-block-html"
    else:
        full_text = ""
        text_source = "none"

    sport = _resolve_sport(raw, url)
    if not sport:
        log.warning("Skip %s: could not resolve sport", url)
        return None

    competition = (raw.get("competition") or "").strip()

    bets = _parse_bets(raw.get("betsDom") or [])
    if not bets:
        log.info("Skip %s: no bets with odds", url)
        return None

    author = (raw.get("author") or "").strip()
    published_at = match_date
    pub_raw = (raw.get("datePublished") or "").strip()
    if pub_raw:
        pub_dt = parse_schema_start_date(pub_raw, geo=SOURCE_CONFIG.get("geo"))
        if pub_dt:
            published_at = pub_dt

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
        "published_at": published_at,
        "bets": bets,
        "meta": raw.get("meta"),
        "content_html": clean_article_html(content_html) if content_html else "",
        "text_source": text_source,
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
                    ft = (data.get("full_text") or "").strip()
                    preview = ft[:220].replace("\n", " ") if ft else ""
                    if len(ft) > 220:
                        preview += "…"
                    print(
                        f"  full_text:  {len(ft)} chars ({data.get('text_source', '?')})"
                    )
                    if preview:
                        print(f"  preview:    {preview}")
                    print(f"  bets:       {len(data.get('bets') or [])}")
                    for b in data.get("bets") or []:
                        print(f"    - {b.get('bet_pick')} @ {b.get('odds')}")


def main() -> None:
    from src.config import setup_logging

    setup_logging()
    parser = argparse.ArgumentParser(description="Betonmobile.ru parser tests")
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
