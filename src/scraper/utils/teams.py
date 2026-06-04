"""Извлечение названий команд из заголовков статей."""
from __future__ import annotations

import re

# Хвосты заголовков прогнозов (RO: Legalbet/Beturi; RU: Metaratings и др.)
_TITLE_SUFFIX = re.compile(
    r"\s*:\s*(?:Ponturi|cele mai bune|pronostic|прогноз|ставк).*$"
    r"|\s+[—–]\s+(?:Ponturi|cele mai bune|pronostic|прогноз).*$"
    r"|\s+ponturi\s+pariuri.*$|\s+pronostic.*$|\s+pariuri\s+.*$"
    r"|\s+прогноз\s+на\s+.*$"
    r"|\s+прогнозы\s+и\s+ставки.*$"
    r"|\s*\.\s+Ставка\s+.*$"
    r"|\s+ставка\s+с\s+коэффициентом\s+.*$",
    re.I,
)

# Разделитель только em/en dash (не дефис в фамилии Auger-Aliassime)
_DASH_SPLIT = re.compile(r"\s+[—–]\s+")
# Обычный дефис с пробелами (stavkiprognozy.ru: «Словения - Кипр»)
_HYPHEN_SPLIT = re.compile(r"\s+-\s+")
_VS_SPLIT = re.compile(r"\s+vs\s+", re.I)


def parse_teams_from_title(title: str) -> tuple[str, str]:
    """Команды из h1: «Georgia — România ponturi…», «A vs B» или «A - B»."""
    clean = _TITLE_SUFFIX.sub("", (title or "").strip())
    clean = re.sub(r"[«»]", "", clean)
    if not clean:
        return "", ""
    if ":" in clean:
        clean = clean.split(":", 1)[0].strip()

    if _VS_SPLIT.search(clean):
        parts = _VS_SPLIT.split(clean, maxsplit=1)
        if len(parts) == 2:
            return parts[0].strip(), _trim_away(parts[1])

    if _DASH_SPLIT.search(clean):
        parts = _DASH_SPLIT.split(clean, maxsplit=1)
        if len(parts) == 2:
            return parts[0].strip(), _trim_away(parts[1])

    if _HYPHEN_SPLIT.search(clean):
        parts = _HYPHEN_SPLIT.split(clean, maxsplit=1)
        if len(parts) == 2:
            return parts[0].strip(), _trim_away(parts[1])

    return "", ""


def parse_teams_from_preview(text: str) -> tuple[str, str]:
    """
    Строка над датой на Legalbet: «Thailanda (F) vs Serbia (F)\\n3 iunie, 10:00».
    """
    if not text:
        return "", ""
    head = text[:800]
    m = re.search(
        r"^([A-Za-zÀ-ÿ0-9 .'()‑-]{2,60}?)\s+vs\s+([A-Za-zÀ-ÿ0-9 .'()‑-]{2,60}?)\s*$",
        head,
        re.I | re.M,
    )
    if m:
        return m.group(1).strip(), m.group(2).strip()
    m = re.search(
        r"^([A-Za-zÀ-ÿ0-9 .'()‑-]{2,60}?)\s+[—–]\s+([A-Za-zÀ-ÿ0-9 .'()‑-]{2,60}?)\s*$",
        head,
        re.M,
    )
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return "", ""


def _trim_away(away: str) -> str:
    away = away.strip()
    away = re.sub(r"\s*:\s*прогноз.*$", "", away, flags=re.I)
    away = re.sub(r"\s+прогноз\s+на\s+.*$", "", away, flags=re.I)
    away = re.sub(r"\s+прогнозы\s+и\s+ставки.*$", "", away, flags=re.I)
    away = re.sub(r"\s+ставка\s+.*$", "", away, flags=re.I)
    away = re.sub(r"\s+с\s+коэффициентом\s+.*$", "", away, flags=re.I)
    away = re.sub(r"\s+\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4}.*$", "", away)
    away = re.sub(r",\s+.*$", "", away)
    return away.strip()


def sanitize_team_label(name: str) -> str:
    """Убирает хвосты из полей schema/h1 (прогноз, ставка, дата матча)."""
    s = (name or "").strip()
    if not s:
        return ""
    s = _TITLE_SUFFIX.sub("", s)
    return _trim_away(s)
