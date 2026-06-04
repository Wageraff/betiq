"""Нормализация команд, match_key и дедупликация матчей."""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Match
from src.db.teams import get_or_create_team

CLUB_PREFIXES = re.compile(r"\b(fc|fk|sc|ac|sk|bk|if|afc|cf|rc)\b", re.I)

# Кириллица → латиница (для legalbet.ru и др.)
_CYRILLIC_MAP = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "sch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}

# Канонические имена после normalize (RO/RU/EN варианты → один ключ)
_TEAM_ALIASES: dict[str, str] = {
    "franta": "france",
    "frantsiya": "france",
    "franciya": "france",
    "coastadefildes": "ivorycoast",
    "coastadefildei": "ivorycoast",
    "kotdivuar": "ivorycoast",
    "kotdivoire": "ivorycoast",
    "cotedivoire": "ivorycoast",
}


def _transliterate_cyrillic(text: str) -> str:
    out: list[str] = []
    for ch in text:
        low = ch.lower()
        if "\u0400" <= ch <= "\u04ff" or "\u0500" <= ch <= "\u052f":
            out.append(_CYRILLIC_MAP.get(low, ""))
        else:
            out.append(ch)
    return "".join(out)


def normalize_team_name(name: str) -> str:
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    name = _transliterate_cyrillic(name)
    name = name.lower()
    name = CLUB_PREFIXES.sub("", name)
    name = re.sub(r"[^a-z0-9]", "", name)
    name = name.strip()
    return _TEAM_ALIASES.get(name, name)


def build_match_key(team_home: str, team_away: str, match_date: date) -> str:
    home = normalize_team_name(team_home)
    away = normalize_team_name(team_away)
    return f"{home}:{away}:{match_date.isoformat()}"


def build_slug(team_home: str, team_away: str, match_date: date) -> str:
    home = normalize_team_name(team_home)
    away = normalize_team_name(team_away)
    return f"{home}-vs-{away}-{match_date.strftime('%d-%m-%Y')}"


def _refresh_match_fields(match: Match, data: dict) -> None:
    """Обновить поля матча при повторном парсинге (sport, competition, команды)."""
    if data.get("team_home"):
        match.team_home = data["team_home"]
    if data.get("team_away"):
        match.team_away = data["team_away"]
    if data.get("sport"):
        match.sport = data["sport"]
    if data.get("competition") is not None:
        match.competition = data["competition"] or match.competition
    if data.get("match_date"):
        match.match_date = data["match_date"]
        day = _as_date(data["match_date"])
        match.slug = build_slug(data["team_home"], data["team_away"], day)
        match.match_key = build_match_key(data["team_home"], data["team_away"], day)


def _as_date(value: date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    return value


async def _link_teams(session: AsyncSession, match: Match, data: dict) -> None:
    sport = data.get("sport")
    home = await get_or_create_team(session, data["team_home"], sport=sport)
    away = await get_or_create_team(session, data["team_away"], sport=sport)
    match.team_home_id = home.id
    match.team_away_id = away.id


async def find_or_create_match(session: AsyncSession, data: dict) -> Match:
    """Найти существующий матч по ключу или создать новый."""
    match_dt: datetime = data["match_date"]
    day = _as_date(match_dt)
    key = build_match_key(data["team_home"], data["team_away"], day)

    match = await session.scalar(select(Match).where(Match.match_key == key))
    if match:
        _refresh_match_fields(match, data)
        await _link_teams(session, match, data)
        return match

    home_norm = normalize_team_name(data["team_home"])
    away_norm = normalize_team_name(data["team_away"])
    day_start = datetime.combine(day - timedelta(days=1), datetime.min.time())
    day_end = datetime.combine(day + timedelta(days=1), datetime.max.time())

    match = await session.scalar(
        select(Match).where(
            Match.match_key.like(f"{home_norm}:{away_norm}:%"),
            Match.match_date >= day_start,
            Match.match_date <= day_end,
        )
    )
    if match:
        _refresh_match_fields(match, data)
        await _link_teams(session, match, data)
        return match

    match = Match(
        match_key=key,
        team_home=data["team_home"],
        team_away=data["team_away"],
        sport=data.get("sport"),
        competition=data.get("competition"),
        match_date=match_dt,
        slug=build_slug(data["team_home"], data["team_away"], day),
    )
    session.add(match)
    await session.flush()
    await _link_teams(session, match, data)
    return match
