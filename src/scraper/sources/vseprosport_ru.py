"""Парсер vseprosport.ru — разделы /news/{sport}/.

См. instructions/vseprosport_ru.md: SportsEvent + NewsArticle (JSON-LD),
category-head (турнир), matchAnnounce / prediction-section / expert-tip (ставки).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import re
from datetime import date, datetime
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

log = logging.getLogger("vseprosport_ru")

SOURCE_CONFIG = {
    "name": "vseprosport.ru",
    "base_url": "https://www.vseprosport.ru",
    "category_url": "/news/football",
    "language": "ru",
    "geo": "RU",
}

VPS_SECTIONS: list[dict[str, Any]] = [
    {"key": "football", "path": "/news/football", "sport": "football"},
    {"key": "hockey", "path": "/news/hockey", "sport": "hockey"},
    {"key": "tennis", "path": "/news/tennis", "sport": "tennis"},
    {"key": "basketball", "path": "/news/basketball", "sport": "basketball"},
    {"key": "volleyball", "path": "/news/volleyball", "sport": "volleyball"},
    {"key": "handball", "path": "/news/handball", "sport": "handball"},
]

_URL_SPORT_HINT: dict[str, str] = {}

_NEWS_ARTICLE_PATH = re.compile(
    r"/news/\d{4}/\d{2}/\d{2}/[^/]+$",
    re.I,
)

_SKIP_URL = re.compile(
    r"/news/(?:football|hockey|tennis|basketball|volleyball|handball)/?$"
    r"|/transfers/|/rating/|/bookmakers/",
    re.I,
)

_TEST_URLS = [
    (
        "football",
        "https://www.vseprosport.ru/news/2026/06/03/iran-mali-stavka-konstantina-ulanova-4-ijunja-2026-goda",
    ),
    (
        "tennis",
        "https://www.vseprosport.ru/news/2026/06/04/karol-vrzevieki-zdenek-kolar-prognoz-kf-1-42-i-stavki-na-match-prosteev-04-iyunya-2026-goda-ot-vps",
    ),
    (
        "hockey",
        "https://www.vseprosport.ru/news/2026/06/04/karolina-vegas-prognoz-kf-2-07-i-stavki-na-match-nhl-5-ijunja-2026-goda",
    ),
]

_COLLECT_JS = """
() => {
  const skip = /\\/news\\/(football|hockey|tennis|basketball|volleyball|handball)\\/?$/i;
  const articlePath = /\\/news\\/\\d{4}\\/\\d{2}\\/\\d{2}\\/[^/]+$/i;
  const slugHint = /prognoz|stavka|stavki|match|kf-|tovarish/i;
  const out = new Set();
  for (const a of document.querySelectorAll('a[href]')) {
    let href = a.href.split('#')[0].split('?')[0].replace(/\\/$/, '');
    if (!href.includes('vseprosport.ru')) continue;
    if (!articlePath.test(href)) continue;
    if (skip.test(href)) continue;
    const slug = href.split('/').pop() || '';
    if (slug.length < 20 || !slugHint.test(slug)) continue;
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

  const teamName = (t) => {
    if (!t) return '';
    if (typeof t === 'string') return t.trim();
    return (t.name || '').trim();
  };

  const personName = (p) => {
    if (!p) return '';
    if (typeof p === 'string') return p.trim();
    if (Array.isArray(p)) {
      for (const item of p) {
        const n = personName(item);
        if (n) return n;
      }
      return '';
    }
    return (p.name || '').trim();
  };

  let event = null;
  let article = null;
  for (const script of document.querySelectorAll('script[type="application/ld+json"]')) {
    try {
      const data = JSON.parse(script.textContent || '');
      if (!event) event = findByType(data, 'SportsEvent');
      if (!article) article = findByType(data, 'NewsArticle');
    } catch (e) {}
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
    competition = (event.name || '').trim();
  }

  const catSpan = document.querySelector(
    '.category-head .flex-1 span, .category-head .gap-8 span, .category-head span'
  );
  if (catSpan) {
    const catText = (catSpan.innerText || '').trim().replace(/\\s+/g, ' ');
    if (catText) competition = catText;
  }

  let pageSport = '';
  const sportRx = {
    football: /\\/news\\/football/i,
    hockey: /\\/news\\/hockey/i,
    tennis: /\\/news\\/tennis/i,
    basketball: /\\/news\\/basketball/i,
    volleyball: /\\/news\\/volleyball/i,
    handball: /\\/news\\/handball/i,
  };
  for (const a of document.querySelectorAll(
    '.category-head a[href], .breadcrumb a[href], nav a[href], a[href*="/news/"]'
  )) {
    const href = a.getAttribute('href') || '';
    for (const [sp, rx] of Object.entries(sportRx)) {
      if (rx.test(href)) {
        pageSport = sp;
        break;
      }
    }
    if (pageSport) break;
  }

  const h1 = document.querySelector('h1')?.innerText?.trim() || headline || '';
  const meta = {
    title: getMeta('meta[property="og:title"]') || document.title || '',
    description: getMeta('meta[property="og:description"]') || getMeta('meta[name="description"]'),
  };

  const textBlocks = [];
  const announce = document.querySelector('#matchAnnounce');
  if (announce) textBlocks.push((announce.innerText || '').trim());
  for (const sec of document.querySelectorAll(
    '#prediction-section, section.prediction-section'
  )) {
    const t = (sec.innerText || '').trim();
    if (t) textBlocks.push(t);
  }
  const domText = textBlocks.join('\\n\\n').trim();

  let content_html = '';
  if (!articleBody && textBlocks.length) {
    const htmlParts = [];
    if (announce) htmlParts.push(announce.innerHTML?.trim() || '');
    for (const sec of document.querySelectorAll(
      '#prediction-section, section.prediction-section'
    )) {
      const html = sec.innerHTML?.trim();
      if (html) htmlParts.push(html);
    }
    content_html = htmlParts.filter(Boolean).join('\\n');
  }

  const isNoisePick = (pick) => {
    if (!pick || pick.length > 120) return true;
    if (/прогноз\\s+и\\s+ставки|^прогноз$/i.test(pick)) return true;
    if (/^анализ\\s+команд/i.test(pick)) return true;
    return false;
  };

  const collectBets = (root) => {
    const out = [];
    if (!root) return out;
    const seen = new Set();
    root.querySelectorAll('.coef-tip').forEach((coefEl) => {
      const odds = (coefEl.textContent || '').trim();
      if (!odds || !/[\\d]/.test(odds)) return;
      let pick = '';
      const row = coefEl.closest(
        '.expert-tip, .d-flex, .row, [class*="forecast"], [class*="tip"]'
      ) || coefEl.parentElement;
      const pickEl = row?.querySelector(
        'span.h4.mb-0, span.h4.d-none, span.h4:not(:has(.coef-tip))'
      );
      if (pickEl && !pickEl.contains(coefEl)) {
        pick = (pickEl.textContent || '').trim();
      }
      if (!pick) {
        let prev = coefEl.previousElementSibling;
        while (prev && !pick) {
          if (prev.matches && prev.matches('span.h4')) {
            pick = (prev.textContent || '').trim();
          }
          prev = prev.previousElementSibling;
        }
      }
      pick = pick.replace(/^прогноз\\s*/i, '').trim();
      if (isNoisePick(pick)) return;
      const key = pick + '|' + odds;
      if (pick && !seen.has(key)) {
        seen.add(key);
        out.push({ pick, odds });
      }
    });
    return out;
  };

  const betsDom = [];
  const seenBet = new Set();
  for (const root of [
    document.querySelector('.expert-tip'),
    document.querySelector('#prediction-section'),
    document.querySelector('section.prediction-section'),
  ]) {
    for (const b of collectBets(root)) {
      const key = b.pick + '|' + b.odds;
      if (!seenBet.has(key)) {
        seenBet.add(key);
        betsDom.push(b);
      }
    }
  }

  const betLines = [];
  const betSource = articleBody || domText || '';
  for (const line of betSource.split(/\\n+/)) {
    const t = line.trim().replace(/\\s+/g, ' ');
    if (/^(Прогноз|Ставка)\\s*[—–-]/i.test(t)) betLines.push(t);
  }

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
    pageSport,
    competition,
    content_html,
    betLines,
    betsDom,
    event,
    article,
  };
}
"""

_PATH_SPORT = [
    (re.compile(r"/news/handball", re.I), "handball"),
    (re.compile(r"/news/tennis", re.I), "tennis"),
    (re.compile(r"/news/hockey", re.I), "hockey"),
    (re.compile(r"/news/basketball", re.I), "basketball"),
    (re.compile(r"/news/volleyball", re.I), "volleyball"),
    (re.compile(r"/news/football", re.I), "football"),
]

_BET_LINE = re.compile(
    r"^(?:Прогноз|Ставка)\s*[—–-]\s*(.+?)\s+с\s+коэффициентом\s+([\d.,]+)",
    re.I,
)

_SLUG_SPLIT = re.compile(r"-(?:stavka|prognoz|stavki)-", re.I)

_BET_PICK_NOISE = re.compile(
    r"^прогноз\s+и\s+ставки\s*|^прогноз\s*|анализ\s+команд",
    re.I,
)

_SLUG_SPORT_HINTS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"nhl|hokkej|hockey", re.I), "hockey"),
    (re.compile(r"prosteev|rolan|atp|wta|tennis", re.I), "tennis"),
    (re.compile(r"basket|nba|vtb", re.I), "basketball"),
    (re.compile(r"volley|voley", re.I), "volleyball"),
    (re.compile(r"handball|gandbol", re.I), "handball"),
    (re.compile(r"tovarish|chempionat|futbol|football", re.I), "football"),
]


def _sport_from_url(url: str) -> str:
    for pat, sport in _PATH_SPORT:
        if pat.search(url):
            return sport
    return _URL_SPORT_HINT.get(url.rstrip("/"), "")


def _is_valid_article_url(url: str) -> bool:
    if _SKIP_URL.search(url):
        return False
    if not _NEWS_ARTICLE_PATH.search(urlparse(url).path):
        return False
    slug = urlparse(url).path.rstrip("/").split("/")[-1].lower()
    if len(slug) < 20:
        return False
    if not re.search(r"prognoz|stavka|stavki|match|kf-|tovarish", slug, re.I):
        return False
    return True


def _is_valid_teams(team_home: str, team_away: str) -> bool:
    if not team_home or not team_away or len(team_home) > 80 or len(team_away) > 80:
        return False
    bad = re.compile(r"прогноз|ставк|vseprosport|букмекер|эксперт", re.I)
    return not bad.search(team_home) and not bad.search(team_away)


def _date_from_news_path(url: str) -> Optional[date]:
    m = re.search(r"/news/(\d{4})/(\d{2})/(\d{2})/", url)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return parse_date_from_url(url, geo=SOURCE_CONFIG.get("geo"))


def _clean_team_display(name: str) -> str:
    name = sanitize_team_label((name or "").strip())
    return name.strip(" .,;:")


def _sport_from_slug(url: str) -> str:
    slug = urlparse(url).path.lower()
    for pat, sport in _SLUG_SPORT_HINTS:
        if pat.search(slug):
            return sport
    return ""


def _sport_from_competition(comp: str) -> str:
    c = (comp or "").lower()
    if re.search(r"нхл|\bnhl\b|хоккей|khl", c):
        return "hockey"
    if re.search(r"атп|\bwta\b|простеев|rolan|теннис|tennis", c):
        return "tennis"
    if re.search(r"баскет|втб|\bnba\b", c):
        return "basketball"
    if re.search(r"волейбол|volleyball", c):
        return "volleyball"
    if re.search(r"гандбол|handball", c):
        return "handball"
    if re.search(r"товарищ|футбол|чемпионат|football|liga|лига", c):
        return "football"
    return ""


def _teams_from_slug(url: str) -> tuple[str, str]:
    slug = urlparse(url).path.rstrip("/").split("/")[-1].lower()
    head = _SLUG_SPLIT.split(slug, maxsplit=1)[0]
    head = re.split(r"-kf-\d", head, maxsplit=1)[0]
    head = head.split("-na-match-")[0].split("-ot-vps")[0]
    parts = [p for p in head.split("-") if p and p not in ("kf", "ot")]
    if len(parts) >= 2:
        mid = len(parts) // 2
        home = " ".join(parts[:mid]).title()
        away = " ".join(parts[mid:]).title()
        return home, away
    return "", ""


def _resolve_teams(raw: dict, url: str) -> tuple[str, str]:
    candidates: list[tuple[str, str]] = []

    rh = _clean_team_display(raw.get("team_home") or "")
    ra = _clean_team_display(raw.get("team_away") or "")
    if rh and ra:
        candidates.append((rh, ra))

    meta_title = (raw.get("meta") or {}).get("title") or ""
    for title in (raw.get("h1") or "", meta_title):
        if title:
            th, ta = parse_teams_from_title(title)
            if th and ta:
                candidates.append((th, ta))

    candidates.append(_teams_from_slug(url))

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
    dt = parse_match_datetime(raw.get("h1") or "", url=url, geo=geo)
    if dt:
        return dt
    d = _date_from_news_path(url)
    return default_kickoff_storage(d, geo=geo) if d else None


def _parse_bets(
    bets_dom: list[dict],
    bet_lines: list[str],
    full_text: str,
) -> list[dict]:
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def add(pick: str, odds_raw: str) -> None:
        pick = _BET_PICK_NOISE.sub("", pick)
        pick = re.sub(r"\s+", " ", pick).strip(" ,-«»\"'")
        if not pick or re.search(r"^прогноз\b", pick, re.I):
            return
        odds = parse_odds(odds_raw)
        if odds is None:
            return
        key = (pick, str(odds))
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
        add((item.get("pick") or "").strip(), (item.get("odds") or "").strip())

    lines = list(bet_lines or [])
    if not lines and full_text:
        for line in full_text.splitlines():
            line = line.strip()
            if _BET_LINE.match(line):
                lines.append(line)

    for line in lines:
        m = _BET_LINE.match(line.strip())
        if m:
            add(m.group(1).strip(), m.group(2))

    if not out and full_text:
        m = re.search(
            r"(тотал\s+[^.\\n]{3,80}|победа\s+[^.\\n]{3,60}|"
            r"фора\s*\([^)]+\)[^.\\n]{0,40}|[^.\\n]{5,80})\s+"
            r"(?:за\s+)?(\d{1,2}[.,]\d{2})",
            full_text,
            re.I,
        )
        if m:
            add(m.group(1).strip(), m.group(2))

    return out


def _resolve_sport(raw: dict, url: str) -> str:
    text_sample = " ".join(
        [
            raw.get("competition") or "",
            raw.get("h1") or "",
            (raw.get("domText") or "")[:2000],
            (raw.get("articleBody") or "")[:2000],
        ]
    )
    for candidate in (
        normalize_sport(raw.get("sport") or ""),
        normalize_sport(raw.get("pageSport") or ""),
        _URL_SPORT_HINT.get(url.rstrip("/")),
        _sport_from_url(url),
        _sport_from_slug(url),
        _sport_from_competition(text_sample),
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

    for section in VPS_SECTIONS:
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

    article_body = (raw.get("articleBody") or "").strip()
    dom_text = (raw.get("domText") or "").strip()
    content_html = raw.get("content_html") or ""
    if article_body:
        full_text = article_body
        text_source = "NewsArticle.articleBody"
    elif dom_text:
        full_text = dom_text
        text_source = "matchAnnounce/prediction-section"
    else:
        full_text = html_to_plain_text(clean_article_html(content_html))
        text_source = "workarea-html"

    sport = _resolve_sport(raw, url)
    if not sport:
        log.warning("Skip %s: could not resolve sport", url)
        return None

    competition = (raw.get("competition") or "").strip().rstrip(".")

    bets = _parse_bets(
        raw.get("betsDom") or [],
        raw.get("betLines") or [],
        full_text,
    )
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
                        f"  full_text:  {len(ft)} chars "
                        f"({data.get('text_source', '?')})"
                    )
                    if preview:
                        print(f"  preview:    {preview}")
                    print(f"  bets:       {len(data.get('bets') or [])}")
                    for b in data.get("bets") or []:
                        print(f"    - {b.get('bet_pick')} @ {b.get('odds')}")


def main() -> None:
    from src.config import setup_logging

    setup_logging()
    parser = argparse.ArgumentParser(description="Vseprosport.ru parser tests")
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
