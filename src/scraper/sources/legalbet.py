"""Парсер legalbet.ro — ponturi pariuri."""
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
from src.scraper.utils.teams import parse_teams_from_preview, parse_teams_from_title

# Подписи вида спорта на карточках/статьях Legalbet: «Tenis 2 iunie, 11:02»
_SPORT_LABEL_RE = re.compile(
    r"\b(Fotbal|Tenis|Baschet|Handbal|Hochei|Volei|UFC|MMA)\b",
    re.I,
)

SOURCE_CONFIG = {
    "name": "legalbet.ro",
    "base_url": "https://legalbet.ro",
    "category_url": "/ponturi/",
    "language": "ro",
    "geo": "RO",
}

# Статьи: /ponturi/georgia-romania-ponturi-pariuri-02-06-2026-karbacher/
_SKIP_URL = re.compile(
    r"biletul-zilei|cota-2|sportul-|/arhiva/|ponturile-de-astazi|/maine/|\?page="
    r"|sferturi|meciuri-amicale|cele-mai-bune|pronosticuri-",
    re.I,
)

_INVALID_TEAM_RE = re.compile(
    r"ponturi\s+pariuri|roland\s+garros|meciuri\s+amicale|cele\s+mai\s+bune|"
    r"\bcote\b|pronostic|pariuri\s+sportive",
    re.I,
)

_COLLECT_URLS_JS = """
() => {
  const skip = /biletul-zilei|cota-2|sportul-|\\/arhiva\\/|ponturile-de-astazi|\\/maine\\/|\\?page=/i;
  const out = new Set();
  for (const a of document.querySelectorAll('a[href]')) {
    let href = a.href.split('#')[0].split('?')[0].replace(/\\/$/, '');
    if (!href.includes('legalbet.ro/ponturi/')) continue;
    if (!href.includes('ponturi-pariuri-')) continue;
    if (skip.test(href)) continue;
    out.add(href);
  }
  return [...out];
}
"""

_PARSE_JS = """
() => {
  const h1 = document.querySelector('h1')?.innerText?.trim() || '';
  const metaDate = document.querySelector('time[datetime]')?.getAttribute('datetime')
    || document.querySelector('meta[property="article:published_time"]')?.content
    || '';

  let team_home = '', team_away = '';
  const articleRoot = document.querySelector('article') || document.querySelector('main');
  const contentEl = document.querySelector('.article-content, .post-content') || articleRoot;
  const full_text = articleRoot ? articleRoot.innerText.trim() : (contentEl ? contentEl.innerText.trim() : '');
  const headerBlock = full_text.slice(0, 1500);

  const previewVs = headerBlock.match(
    /([A-Za-zÀ-ÿ0-9 .'()‑-]{2,70})\\s+vs\\s+([A-Za-zÀ-ÿ0-9 .'()‑-]{2,70})\\s*\\n\\s*\\d{1,2}\\s+(?:ian|feb|mar|apr|mai|iun|iul|aug|sep|oct|noi|dec)/i
  );
  if (previewVs) {
    team_home = previewVs[1].trim();
    team_away = previewVs[2].trim();
  } else {
    const cleanH1 = h1.replace(/\\s+ponturi\\s+pariuri.*$/i, '').trim();
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
  }

  let kickoff = '';
  const kickoffM = headerBlock.match(
    /(\\d{1,2})\\s+(ianuarie|februarie|martie|aprilie|mai|iunie|iulie|august|septembrie|octombrie|noiembrie|decembrie)(?:\\s+(\\d{4}))?,?\\s*(\\d{1,2}:\\d{2})/i
  );
  if (kickoffM) kickoff = kickoffM[0];

  let author = '';
  const authorEl = document.querySelector('[class*="tipster"], .author-name, a[href*="/tipster/"]');
  if (authorEl) author = authorEl.textContent?.trim() || '';

  const SPORT_KEYS = new Set(['fotbal','tenis','baschet','handbal','hochei','volei','ufc','mma']);
  const SKIP_CRUMBS = new Set(['acasa','acasă','home','ponturi pariuri','ponturi']);
  const breadcrumbs = [];
  const crumbRoot = document.querySelector(
    '[class*="breadcrumb"], .breadcrumbs, nav[aria-label*="breadcrumb" i]'
  );
  if (crumbRoot) {
    for (const el of crumbRoot.querySelectorAll('li, a')) {
      const t = (el.textContent || '').trim().replace(/\\s+/g, ' ');
      if (!t || SKIP_CRUMBS.has(t.toLowerCase())) continue;
      if (!breadcrumbs.length || breadcrumbs[breadcrumbs.length - 1] !== t) {
        breadcrumbs.push(t);
      }
    }
  }

  let sport = '';
  let competition = '';
  for (let i = 0; i < breadcrumbs.length; i++) {
    const key = breadcrumbs[i].toLowerCase();
    if (SPORT_KEYS.has(key)) {
      sport = key;
      if (breadcrumbs[i + 1] && !SPORT_KEYS.has(breadcrumbs[i + 1].toLowerCase())) {
        competition = breadcrumbs[i + 1];
      }
      break;
    }
  }

  if (!sport) {
    const sportLink = document.querySelector('a[href*="sportul-"]');
    if (sportLink) {
      const sm = sportLink.href.match(/sportul-([a-z0-9-]+)/i);
      if (sm) sport = sm[1].replace(/-/g, ' ');
    }
    const sportLabel = headerBlock.match(/\\b(Fotbal|Tenis|Baschet|Handbal|Hochei|Volei|UFC|MMA)\\b/i);
    if (sportLabel) sport = sportLabel[1].toLowerCase();
  }

  const body = full_text || '';
  if (!competition) {
    const compFromLead = body.match(/meciul din\\s+([^\\n.]{3,80})/i);
    if (compFromLead) competition = compFromLead[1].trim();
    else if (/roland\\s*garros/i.test(body)) competition = 'Roland Garros';
    else if (/wimbledon/i.test(body)) competition = 'Wimbledon';
    else if (/\\b(?:ATP|WTA)\\b/.test(body)) competition = body.match(/\\b(ATP|WTA)[^\\n]{0,30}/i)?.[0]?.trim() || 'ATP/WTA';
    else if (/\\bNBA\\b|WNBA/i.test(body)) competition = body.match(/\\b(NBA|WNBA)\\b/i)?.[0] || 'NBA';
    else {
      const liga = body.match(/Liga[^\\n]{0,60}/i);
      if (liga) competition = liga[0].trim();
    }
  }

  const bets = [];
  const pickBlocks = [...document.querySelectorAll('div, section, article')];
  for (const el of pickBlocks) {
    const t = (el.innerText || '').trim();
    if (t.length > 200 || t.length < 5) continue;
    const lines = t.split('\\n').map(l => l.trim()).filter(Boolean);
    if (!lines.includes('Ponturi') && !lines.includes('Cote')) continue;
    const pickIdx = lines.indexOf('Ponturi');
    const oddsIdx = lines.indexOf('Cote');
    if (pickIdx >= 0 && oddsIdx > pickIdx && lines[pickIdx + 1]) {
      const pick = lines[pickIdx + 1];
      const odds = lines[oddsIdx + 1];
      if (/^[\\d]+[.,][\\d]+$/.test(odds) || /^[\\d.]+$/.test(odds)) {
        bets.push({
          bet_type: '1X2',
          bet_pick: pick,
          odds: odds.replace(',', '.'),
          is_main: bets.length === 0,
        });
      }
    }
  }

  return { h1, metaDate, author, competition, sport, breadcrumbs, kickoff, full_text, team_home, team_away, bets };
}
"""

_CRUMB_SPORTS = frozenset(
    {"fotbal", "tenis", "baschet", "handbal", "hochei", "volei", "ufc", "mma"}
)
_CRUMB_SKIP = frozenset({"acasa", "acasă", "home", "ponturi pariuri", "ponturi"})


def _sport_competition_from_breadcrumbs(crumbs: list[str]) -> tuple[str, str]:
    items = []
    for c in crumbs:
        t = (c or "").strip()
        if not t or t.lower() in _CRUMB_SKIP:
            continue
        if not items or items[-1] != t:
            items.append(t)
    for i, label in enumerate(items):
        key = label.lower()
        if key not in _CRUMB_SPORTS:
            continue
        sport = normalize_sport(label) or key
        competition = ""
        if i + 1 < len(items) and items[i + 1].lower() not in _CRUMB_SPORTS:
            competition = items[i + 1]
        return sport, competition
    return "", ""


def _is_valid_teams(team_home: str, team_away: str) -> bool:
    if not team_home or not team_away:
        return False
    if len(team_home) > 70 or len(team_away) > 70:
        return False
    if team_home.isupper() and len(team_home) > 25:
        return False
    if re.search(r"\d{1,2}\s+iunie\s+\d{4}", team_away, re.I):
        return False
    for name in (team_home, team_away):
        if _INVALID_TEAM_RE.search(name):
            return False
        if name.count(":") >= 1 and len(name) > 35:
            return False
    return True


def _infer_sport(raw_sport: str, full_text: str, title: str) -> str:
    if raw_sport:
        normalized = normalize_sport(raw_sport)
        if normalized:
            return normalized

    blob = f"{title}\n{full_text[:4000]}".lower()
    label = _SPORT_LABEL_RE.search(full_text[:2500] or blob)
    if label:
        return normalize_sport(label.group(1)) or "football"

    if re.search(
        r"roland\s*garros|wimbledon|grand slam|\b(?:atp|wta)\b|game-uri|seturi|tiebreak",
        blob,
    ):
        return "tennis"
    if re.search(r"\b(?:nba|wnba)\b|conferința|puncte per meci|baschet", blob):
        return "basketball"
    if re.search(r"volei|volleyball|liga națiunilor de volei|nations league", blob):
        return "volleyball"
    if re.search(r"cupa mondial|calificări|goluri|offside", blob):
        return "football"
    return "football"


_TENNIS_MARKERS = re.compile(
    r"roland\s*garros|wimbledon|grand slam|\b(?:atp|wta)\b|game-uri|seturi|tiebreak|"
    r"sferturile de finală de la paris",
    re.I,
)


def _finalize_sport_competition(
    sport: str,
    competition: str,
    full_text: str,
    title: str,
    *,
    breadcrumb_sport: bool = False,
) -> tuple[str, str]:
    if breadcrumb_sport and sport not in ("football", ""):
        if competition == "World Cup":
            competition = _infer_competition(full_text, sport)
        return sport, competition

    blob = f"{title}\n{full_text}"

    if _TENNIS_MARKERS.search(blob):
        sport = "tennis"
        if not competition or competition == "World Cup":
            if re.search(r"roland\s*garros", blob, re.I):
                competition = "Roland Garros"
            elif re.search(r"wimbledon", blob, re.I):
                competition = "Wimbledon"
            elif not competition:
                competition = "Grand Slam"

    if sport == "football" and re.search(r"\b(?:nba|wnba)\b|conferința est|conferința vest", blob, re.I):
        sport = "basketball"

    if competition == "World Cup" and sport != "football":
        competition = _infer_competition(full_text, sport)

    if sport == "football" and _TENNIS_MARKERS.search(blob):
        sport = "tennis"
        if not competition or competition == "World Cup":
            competition = "Roland Garros" if re.search(r"roland", blob, re.I) else "Grand Slam"

    return sport, competition


def _infer_competition(full_text: str, sport: str) -> str:
    text = full_text or ""
    m = re.search(r"meciul din\s+([^\n.]{3,60})", text, re.I)
    if m:
        return m.group(1).strip()
    if re.search(r"roland\s*garros", text, re.I):
        return "Roland Garros"
    if re.search(r"wimbledon", text, re.I):
        return "Wimbledon"
    m = re.search(r"\b(ATP|WTA)\b[^\n]{0,30}", text)
    if m and sport == "tennis":
        return m.group(0).strip()
    m = re.search(r"\b(NBA|WNBA)\b", text, re.I)
    if m and sport == "basketball":
        return m.group(1).upper()
    if sport == "football" and re.search(r"cupa mondial|world cup", text, re.I):
        if not re.search(r"volei|volleyball|baschet|tenis", text, re.I):
            return "World Cup"
    m = re.search(r"Liga[^\n]{0,60}", text, re.I)
    if m:
        return m.group(0).strip()
    return ""


async def get_article_urls(page: Page) -> list[str]:
    url = SOURCE_CONFIG["base_url"] + SOURCE_CONFIG["category_url"]
    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    await wait_cloudflare(page)
    urls = await page.evaluate(_COLLECT_URLS_JS)
    filtered = [u for u in urls if not _SKIP_URL.search(u)]
    filtered = [u for u in filtered if _is_valid_article_url(u)]
    return sorted(set(filtered))


def _is_valid_article_url(url: str) -> bool:
    slug = url.rstrip("/").split("/")[-1].lower()
    if "ponturi-pariuri-" not in slug:
        return False
    if not re.search(r"ponturi-pariuri-\d{2}-\d{2}-\d{4}", slug):
        return False
    return True


async def parse_prediction(page: Page, url: str) -> Optional[dict]:
    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    await wait_cloudflare(page)

    raw = await page.evaluate(_PARSE_JS)
    title = (raw or {}).get("h1") or (await page.eval_on_selector("h1", "el => el?.textContent?.trim() || ''"))
    if not title:
        return None

    full_text = (raw or {}).get("full_text") or ""
    team_home = (raw or {}).get("team_home") or ""
    team_away = (raw or {}).get("team_away") or ""
    if not team_home:
        team_home, team_away = parse_teams_from_preview(full_text)
    if not team_home:
        team_home, team_away = parse_teams_from_title(title)

    match_date = parse_match_datetime(
        (raw or {}).get("kickoff") or (raw or {}).get("metaDate") or full_text[:1200],
        url=url,
    )
    if not match_date:
        match_date = parse_date((raw or {}).get("metaDate"))
    if not match_date:
        d = parse_date_from_url(url)
        if d:
            match_date = default_kickoff_utc(d)

    if not match_date:
        return None

    if not team_home or not team_away:
        return None

    if not _is_valid_teams(team_home, team_away):
        return None

    bets = []
    for i, b in enumerate((raw or {}).get("bets") or []):
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

    author = (raw or {}).get("author") or ""
    if not author:
        m = re.search(r"-([a-z]+)/?$", url)
        if m:
            author = m.group(1).replace("-", " ").title()

    crumbs = (raw or {}).get("breadcrumbs") or []
    bc_sport, bc_comp = _sport_competition_from_breadcrumbs(crumbs)

    breadcrumb_sport = bool(bc_sport)
    if bc_sport:
        sport = bc_sport
        competition = bc_comp
    else:
        sport = _infer_sport((raw or {}).get("sport") or "", full_text, title)
        competition = (raw or {}).get("competition") or ""

    if not competition:
        competition = _infer_competition(full_text, sport)
    sport, competition = _finalize_sport_competition(
        sport, competition, full_text, title, breadcrumb_sport=breadcrumb_sport
    )

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
        "published_at": parse_date((raw or {}).get("metaDate")) or match_date,
        "bets": bets,
    }
