"""Парсер stavkiprognozy.ru — разделы /prognozy/{sport}/.

См. instructions/stavkiprognozy_ru.md: SportsEvent + NewsArticle (JSON-LD),
sinfor-main-panel-topbar, box-item-inner / form-group-xl, forecast-bar, inline-ставки.
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

log = logging.getLogger("stavkiprognozy_ru")

SOURCE_CONFIG = {
    "name": "stavkiprognozy.ru",
    "base_url": "https://stavkiprognozy.ru",
    "category_url": "/prognozy/football/",
    "language": "ru",
    "geo": "RU",
}

STAVKI_SECTIONS: list[dict[str, Any]] = [
    {"key": "football", "path": "/prognozy/football/", "sport": "football"},
    {"key": "hockey", "path": "/prognozy/hockey/", "sport": "hockey"},
    {"key": "tennis", "path": "/prognozy/tennis/", "sport": "tennis"},
    {"key": "basketball", "path": "/prognozy/basketball/", "sport": "basketball"},
    {"key": "voleybol", "path": "/prognozy/voleybol/", "sport": "volleyball"},
]

_URL_SPORT_HINT: dict[str, str] = {}

_SKIP_SECTION = re.compile(
    r"/prognozy/(?:football|hockey|tennis|basketball|voleybol)/?$",
    re.I,
)

_PRO_ARTICLE = re.compile(r"/prognozy/[^/]+/[^/]+/pro_prognoz-", re.I)

_TEST_URLS = [
    (
        "football",
        "https://stavkiprognozy.ru/prognozy/football/tovarishcheskie-matchi-sbornykh/pro_prognoz-sloveniya-kipr-4-iyunya-2026",
    ),
    (
        "hockey",
        "https://stavkiprognozy.ru/prognozy/hockey/nkhl/pro_prognoz-karolina-kharikeyns-vegas-golden-nayts-5-iyunya-2026",
    ),
    (
        "tennis",
        "https://stavkiprognozy.ru/prognozy/tennis/rolan-garros/pro_prognoz-diana-shnayder-mayya-khvalinska-4-iyunya-2026g",
    ),
    (
        "basketball",
        "https://stavkiprognozy.ru/prognozy/basketball/edinaya-liga-vtb/pro_prognoz-tsska-uniks-4-iyunya-2026g",
    ),
]

_COLLECT_JS = """
() => {
  const skip = /\\/prognozy\\/(football|hockey|tennis|basketball|voleybol)\\/?$/i;
  const out = new Set();
  for (const a of document.querySelectorAll('a[href]')) {
    let href = a.href.split('#')[0].split('?')[0].replace(/\\/$/, '');
    if (!href.includes('stavkiprognozy.ru')) continue;
    if (!href.includes('/prognozy/')) continue;
    if (skip.test(href)) continue;
    if (!/pro_prognoz/i.test(href)) continue;
    try {
      const parts = new URL(href).pathname.split('/').filter(Boolean);
      if (parts.length < 4) continue;
    } catch (e) { continue; }
    out.add(href);
  }
  return [...out];
}
"""

_PARSE_JS = """
() => {
  const getMeta = (sel) => document.querySelector(sel)?.getAttribute('content')?.trim() || '';

  const hasType = (obj, typeName) => {
    const t = obj && obj['@type'];
    if (!t) return false;
    if (t === typeName) return true;
    return Array.isArray(t) && t.includes(typeName);
  };

  const findByType = (obj, typeName) => {
    if (!obj) return null;
    if (Array.isArray(obj)) {
      for (const item of obj) {
        const found = findByType(item, typeName);
        if (found) return found;
      }
      return null;
    }
    if (hasType(obj, typeName)) return obj;
    if (obj['@graph']) return findByType(obj['@graph'], typeName);
    return null;
  };

  const ldNodes = [];
  const collectLdNodes = (obj) => {
    if (!obj) return;
    if (Array.isArray(obj)) {
      obj.forEach(collectLdNodes);
      return;
    }
    ldNodes.push(obj);
    if (obj['@graph']) collectLdNodes(obj['@graph']);
  };

  const ldById = () => {
    const m = new Map();
    for (const n of ldNodes) {
      if (n && n['@id']) m.set(n['@id'], n);
    }
    return m;
  };

  const teamName = (t, byId) => {
    if (!t) return '';
    if (typeof t === 'string') {
      const node = byId && byId.get(t);
      return node ? (node.name || '').trim() : t.trim();
    }
    if (Array.isArray(t)) {
      for (const item of t) {
        const n = teamName(item, byId);
        if (n) return n;
      }
      return '';
    }
    return (t.name || teamName(t['@id'], byId) || '').trim();
  };

  const entityName = (t) => teamName(t, null);

  const teamsFromLine = (line) => {
    const t = (line || '').trim().replace(/[«»"']/g, '').replace(/\\s+/g, ' ');
    if (!t) return null;
    const head = t.split(':')[0].trim();
    const m = head.match(/^(.+?)\\s+-\\s+(.+)$/);
    if (!m) return null;
    return { home: m[1].trim(), away: m[2].trim() };
  };

  const personName = (author) => {
    if (!author) return '';
    if (typeof author === 'string') return author.trim();
    if (Array.isArray(author)) {
      for (const item of author) {
        const n = personName(item);
        if (n) return n;
      }
      return '';
    }
    if (hasType(author, 'Person')) return (author.name || '').trim();
    return entityName(author);
  };

  let event = null;
  let article = null;
  for (const script of document.querySelectorAll('script[type="application/ld+json"]')) {
    try {
      const data = JSON.parse(script.textContent || '');
      collectLdNodes(data);
      if (!event) event = findByType(data, 'SportsEvent');
      if (!article) article = findByType(data, 'NewsArticle');
    } catch (e) {}
  }
  const byId = ldById();

  let team_home = '';
  let team_away = '';
  let kickoff = '';
  let sport = '';
  let location = '';
  let competition = '';

  if (event) {
    kickoff = event.startDate || '';
    sport = event.sport || '';
    team_home = teamName(event.homeTeam, byId);
    team_away = teamName(event.awayTeam, byId);
    if (!team_home && Array.isArray(event.competitor) && event.competitor.length >= 2) {
      team_home = teamName(event.competitor[0], byId);
      team_away = teamName(event.competitor[1], byId);
    }
    location = teamName(event.location, byId) || entityName(event.location);
    competition = (event.name || '').trim();
  }

  if (!team_home) {
    team_home = document.querySelector('[itemprop="homeTeam"] meta[itemprop="name"]')?.getAttribute('content')
      || document.querySelector('[itemprop="homeTeam"]')?.textContent?.trim() || '';
  }
  if (!team_away) {
    team_away = document.querySelector('[itemprop="awayTeam"] meta[itemprop="name"]')?.getAttribute('content')
      || document.querySelector('[itemprop="awayTeam"]')?.textContent?.trim() || '';
  }

  let author = '';
  let articleBody = '';
  let headline = '';
  let datePublished = '';
  if (article) {
    author = personName(article.author);
    if (typeof article.articleBody === 'string') {
      articleBody = article.articleBody.trim();
    }
    headline = (article.headline || article.name || '').trim();
    datePublished = article.datePublished || article.dateModified || '';
  }

  const topbarInner = document.querySelector(
    '.sinfor-main-panel-topbar-inner, .sinfor-main-panel-topbar .sinfor-main-panel-topbar-inner'
  );
  if (topbarInner) {
    const divs = [...topbarInner.querySelectorAll(':scope > div')];
    for (const div of divs) {
      if (!team_home || !team_away) {
        const pair = teamsFromLine(div.innerText);
        if (pair) {
          team_home = team_home || pair.home;
          team_away = team_away || pair.away;
        }
      }
    }
    const last = divs[divs.length - 1];
    if (last) {
      const t = (last.innerText || '').trim().replace(/\\s+/g, ' ');
      if (t && !/\\s+-\\s+/.test(t)) competition = t;
      else if (t && !competition) competition = t;
    }
  }

  const meta = {
    title: getMeta('meta[property="og:title"]') || document.title || '',
    description: getMeta('meta[property="og:description"]') || getMeta('meta[name="description"]'),
  };

  const h1 = document.querySelector('h1')?.innerText?.trim() || headline || '';
  if ((!team_home || !team_away) && h1) {
    const pair = teamsFromLine(h1);
    if (pair) {
      team_home = team_home || pair.home;
      team_away = team_away || pair.away;
    }
  }
  if ((!team_home || !team_away) && meta.title) {
    const pair = teamsFromLine(meta.title);
    if (pair) {
      team_home = team_home || pair.home;
      team_away = team_away || pair.away;
    }
  }

  const SKIP_IDS = ['fc-coeffs', 'fc-private-matches', 'last-matches', 'fc-live'];
  const NOISE_SEL = [
    '.forecast-bar', '.alternate-item', '.alternate-item-title',
    '.sinfor-main-panel-topbar', 'script', 'style', 'iframe', 'nav', 'footer',
  ].join(', ');

  const stripSkipBlocks = (root) => {
    const clone = root.cloneNode(true);
    for (const id of SKIP_IDS) {
      clone.querySelectorAll('#' + id).forEach((el) => el.remove());
    }
    clone.querySelectorAll(NOISE_SEL).forEach((el) => el.remove());
    return clone;
  };

  const rootText = (root) => {
    if (!root) return '';
    return (stripSkipBlocks(root).innerText || '').trim().replace(/\\s+/g, ' ');
  };

  const textParts = [];
  let content_html = '';
  const box =
    document.querySelector('.box-item-inner')
    || document.querySelector('.box-item .box-item-inner')
    || document.querySelector('.box-item');

  if (box) {
    const whole = rootText(box);
    if (whole.length > 200) textParts.push(whole);
    if (!articleBody) {
      content_html = stripSkipBlocks(box).innerHTML?.trim() || '';
    }
  }

  if (!textParts.length) {
    for (const fg of document.querySelectorAll('.form-group-xl, .form-group')) {
      if (SKIP_IDS.includes(fg.id)) continue;
      const t = rootText(fg);
      if (t.length > 80) textParts.push(t);
      if (!articleBody && !content_html && t.length > 80) {
        content_html = stripSkipBlocks(fg).innerHTML?.trim() || '';
      }
    }
  }

  if (!textParts.length) {
    const h1El = document.querySelector('h1');
    let el = h1El?.nextElementSibling;
    const walk = [];
    while (el && walk.join('').length < 80000) {
      const tag = (el.tagName || '').toLowerCase();
      if (tag === 'h1' || el.classList?.contains('sinfor-main-panel-topbar')) break;
      const t = rootText(el);
      if (t.length > 80) walk.push(t);
      el = el.nextElementSibling;
    }
    if (walk.length) textParts.push(walk.join('\\n\\n'));
  }

  const domText = [...new Set(textParts)].join('\\n\\n').trim();

  const betsDom = [];
  const seenBet = new Set();
  const pushBet = (pick, odds) => {
    pick = (pick || '').trim().replace(/\\s+/g, ' ');
    odds = (odds || '').trim();
    const om = odds.match(/(\\d{1,2}[.,]\\d{2})/);
    if (!pick || !om) return;
    odds = om[1];
    const key = pick + '|' + odds;
    if (seenBet.has(key)) return;
    seenBet.add(key);
    betsDom.push({ pick, odds });
  };

  document.querySelectorAll('.forecast-bar').forEach((bar) => {
    const grid = bar.querySelector('.forecast-bar-values-grid');
    const values = grid ? [...grid.querySelectorAll('.forecast-bar-value')] : [];
    const pickEl = values.length >= 2 ? values[1] : values[0];
    const coeffEl = bar.querySelector('.forecast-bar-value-coeff');
    if (pickEl) {
      pushBet(pickEl.textContent, coeffEl ? coeffEl.textContent : '');
    }
  });

  document.querySelectorAll('.alternate-item-title').forEach((titleEl) => {
    const row = titleEl.closest('[class*="alternate"]') || titleEl.parentElement;
    const coeffEl = row?.querySelector('.alternate-item-coeff-value')
      || titleEl.parentElement?.querySelector('.alternate-item-coeff-value');
    pushBet(titleEl.textContent, coeffEl ? coeffEl.textContent : '');
  });

  document.querySelectorAll(
    'span[style*="#e9fff5"], span[style*="e9fff5"], span[style*="254b3c"]'
  ).forEach((el) => {
    const raw = (el.innerText || el.textContent || '').trim();
    let m = raw.match(/\\{([^}]+)\\}\\s*за\\s*\\{([\\d.,]+)\\}/i);
    if (m) {
      pushBet(m[1], m[2]);
      return;
    }
    m = raw.match(/^(.+?)\\s+за\\s+([\\d.,]+)$/i);
    if (m) pushBet(m[1], m[2]);
  });

  return {
    h1,
    meta,
    author,
    articleBody,
    datePublished,
    domText,
    team_home,
    team_away,
    kickoff,
    sport,
    location,
    competition,
    content_html,
    betsDom,
    event,
    article,
  };
}
"""

_PATH_SPORT = [
    (re.compile(r"/prognozy/tennis/", re.I), "tennis"),
    (re.compile(r"/prognozy/hockey/", re.I), "hockey"),
    (re.compile(r"/prognozy/basketball/", re.I), "basketball"),
    (re.compile(r"/prognozy/voleybol/", re.I), "volleyball"),
    (re.compile(r"/prognozy/football/", re.I), "football"),
]

_INLINE_BET = re.compile(
    r"(\{([^}]+)\}|([^.{}\n]{5,90}?))\s+за\s+(\d{1,2}[.,]\d{2})\b",
    re.I,
)
_SPAN_BET = re.compile(r"\{([^}]+)\}\s*за\s*\{([\d.,]+)\}", re.I)
_LINE_BET = re.compile(
    r"^[-•]?\s*(.+?)\s+за\s+(\d{1,2}[.,]\d{2})\s*$",
    re.I | re.M,
)


def _sport_from_url(url: str) -> str:
    for pat, sport in _PATH_SPORT:
        if pat.search(url):
            return sport
    return _URL_SPORT_HINT.get(url.rstrip("/"), "")


def _is_valid_article_url(url: str) -> bool:
    if _SKIP_SECTION.search(urlparse(url).path):
        return False
    return bool(_PRO_ARTICLE.search(url))


def _is_valid_teams(team_home: str, team_away: str) -> bool:
    if not team_home or not team_away or len(team_home) > 80 or len(team_away) > 80:
        return False
    bad = re.compile(r"прогноз|ставк|stavkiprognozy|букмекер", re.I)
    return not bad.search(team_home) and not bad.search(team_away)


def _clean_team_display(name: str) -> str:
    name = sanitize_team_label((name or "").strip())
    name = name.strip(" «»\"'")
    return name


def _resolve_teams(raw: dict, url: str) -> tuple[str, str]:
    candidates: list[tuple[str, str]] = []

    rh = _clean_team_display(raw.get("team_home") or "")
    ra = _clean_team_display(raw.get("team_away") or "")
    if rh and ra:
        candidates.append((rh, ra))

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
    kickoff = (raw.get("kickoff") or "").strip()
    if kickoff:
        dt = parse_schema_start_date(kickoff, geo=geo)
        if dt:
            return dt
        dt = parse_match_datetime(kickoff, url=url, geo=geo)
        if dt:
            return dt
    for src in (raw.get("h1") or "", raw.get("meta", {}).get("title") or ""):
        dt = parse_match_datetime(src, url=url, geo=geo)
        if dt:
            return dt
    path = re.sub(r"(\d{4})g\b", r"\1", urlparse(url).path, flags=re.I)
    d = parse_date_from_url(path, geo=geo) or parse_date_from_url(url, geo=geo)
    return default_kickoff_storage(d, geo=geo) if d else None


def _clean_bet_pick(pick: str) -> str:
    pick = (pick or "").strip().strip("{}")
    pick = re.sub(r"\s+", " ", pick)
    pick = pick.strip(" ,-«»\"'")
    if len(pick) < 4:
        return ""
    if re.search(r"^(?:коэффициент|ставка|букмекер)\b", pick, re.I):
        return ""
    return pick


def _bet_pick_key(pick: str, odds: str) -> str:
    p = pick.lower()
    p = re.sub(r"мячей", "голов", p)
    p = re.sub(r"[«»\"'–—]", "", p)
    p = re.sub(r"\s*фор[аы]\s*1\b", " фора1 ", p)
    p = re.sub(r"\s*фор[аы]\s*2\b", " фора2 ", p)
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


def _bets_from_full_text(full_text: str) -> list[tuple[str, str]]:
    if not full_text:
        return []
    found: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(pick: str, odds: str) -> None:
        pick = _clean_bet_pick(pick)
        if not pick:
            return
        key = _bet_pick_key(pick, odds)
        if key in seen:
            return
        seen.add(key)
        found.append((pick, odds))

    for m in _SPAN_BET.finditer(full_text):
        add(m.group(1), m.group(2))

    for m in _INLINE_BET.finditer(full_text):
        pick = m.group(2) or m.group(3) or ""
        add(pick, m.group(4))

    for m in _LINE_BET.finditer(full_text):
        add(m.group(1), m.group(2))

    return found


def _parse_bets(bets_dom: list[dict], full_text: str) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()

    def add(pick: str, odds_raw: str) -> None:
        pick = _clean_bet_pick(pick)
        odds = parse_odds(odds_raw)
        if not pick or odds is None:
            return
        key = _bet_pick_key(pick, str(odds))
        if key in seen:
            return
        seen.add(key)
        out.append(
            {
                "bet_type": "1X2",
                "bet_pick": pick,
                "odds": odds,
                "is_main": len(out) == 0,
            }
        )

    for item in bets_dom or []:
        add(item.get("pick") or "", item.get("odds") or "")

    for pick, odds_raw in _bets_from_full_text(full_text):
        add(pick, odds_raw)

    return _dedupe_bets(out)


def _resolve_sport(raw: dict, url: str) -> str:
    competition = (raw.get("competition") or "").strip()
    body = " ".join(
        [
            competition,
            raw.get("h1") or "",
            (raw.get("domText") or "")[:3000],
            (raw.get("articleBody") or "")[:3000],
        ]
    )
    slug = urlparse(url).path.lower()
    for candidate in (
        _sport_from_url(url),
        _URL_SPORT_HINT.get(url.rstrip("/")),
        normalize_sport(raw.get("sport") or ""),
        normalize_sport(competition),
        normalize_sport(raw.get("location") or ""),
    ):
        if candidate:
            return candidate
    if re.search(r"nhl|nkhl|хоккей", slug + body, re.I):
        return "hockey"
    if re.search(r"rolan|garros|теннис|atp|wta", slug + body, re.I):
        return "tennis"
    if re.search(r"vtb|баскет", slug + body, re.I):
        return "basketball"
    if re.search(r"товарищ|футбол|football", slug + body, re.I):
        return "football"
    return ""


def _resolve_competition(raw: dict) -> str:
    comp = (raw.get("competition") or "").strip()
    if comp and not re.search(r"прогноз|ставк", comp, re.I):
        return comp
    title = (raw.get("meta") or {}).get("title") or ""
    m = re.search(r"\(([^)]+)\)\s*$", title)
    if m:
        return m.group(1).strip()
    return comp


async def _activate_prognoz_tab(page: Any) -> None:
    """Контент прогноза часто во вкладке «Прогноз» — без клика box-item-inner пустой."""
    selectors = (
        'a[href="#prognoz"]',
        'a[href="#forecast"]',
        '[data-bs-toggle="tab"][href*="prognoz"]',
        '.nav-tabs a:has-text("Прогноз")',
        'button:has-text("Прогноз")',
    )
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0:
                await loc.click(timeout=5000)
                await page.wait_for_timeout(600)
                break
        except Exception:
            continue
    else:
        try:
            tab = page.get_by_text("Прогноз", exact=True).first
            if await tab.count() > 0:
                await tab.click(timeout=5000)
                await page.wait_for_timeout(600)
        except Exception:
            pass
    try:
        await page.wait_for_function(
            """() => {
              const b = document.querySelector('.box-item-inner, .box-item');
              return b && (b.innerText || '').replace(/\\s+/g, ' ').trim().length > 400;
            }""",
            timeout=15_000,
        )
    except Exception:
        pass


async def get_article_urls(page: Any) -> list[str]:
    from src.scraper.utils.browser import wait_cloudflare

    global _URL_SPORT_HINT
    _URL_SPORT_HINT = {}
    base = SOURCE_CONFIG["base_url"].rstrip("/")
    found: set[str] = set()

    for section in STAVKI_SECTIONS:
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
    await _activate_prognoz_tab(page)

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

    article_body = (raw.get("articleBody") or "").strip()
    dom_text = (raw.get("domText") or "").strip()
    content_html = raw.get("content_html") or ""
    if article_body:
        full_text = article_body
        text_source = "NewsArticle.articleBody"
    elif dom_text:
        full_text = dom_text
        text_source = "box-item-inner"
    elif content_html:
        full_text = html_to_plain_text(content_html) or html_to_plain_text(
            clean_article_html(content_html)
        )
        text_source = "form-group-html"
    else:
        full_text = ""
        text_source = "none"

    sport = _resolve_sport(raw, url)
    if not sport:
        log.warning("Skip %s: could not resolve sport", url)
        return None

    competition = _resolve_competition(raw)

    bets = _parse_bets(raw.get("betsDom") or [], full_text)
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
        "event_meta": raw.get("event") or {},
        "article_meta": raw.get("article") or {},
        "text_source": text_source,
        "text_debug": {
            "articleBody": len(article_body),
            "domText": len(dom_text),
            "content_html": len(content_html or ""),
        },
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
                    if not ft and data.get("text_debug"):
                        d = data["text_debug"]
                        print(
                            f"  debug:      articleBody={d.get('articleBody')} "
                            f"domText={d.get('domText')} html={d.get('content_html')}"
                        )
                    if preview:
                        print(f"  preview:    {preview}")
                    print(f"  bets:       {len(data.get('bets') or [])}")
                    for b in data.get("bets") or []:
                        print(f"    - {b.get('bet_pick')} @ {b.get('odds')}")


def main() -> None:
    from src.config import setup_logging

    setup_logging()
    parser = argparse.ArgumentParser(description="Stavkiprognozy.ru parser tests")
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
