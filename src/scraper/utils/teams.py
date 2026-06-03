"""Извлечение названий команд из заголовков статей."""
from __future__ import annotations

import re

# Хвосты румынских заголовков прогнозов (Legalbet, Beturi и др.)
_TITLE_SUFFIX = re.compile(
    r"\s*:\s*(?:Ponturi|cele mai bune|pronostic).*$"
    r"|\s+[—–]\s+(?:Ponturi|cele mai bune|pronostic).*$"
    r"|\s+ponturi\s+pariuri.*$|\s+pronostic.*$|\s+pariuri\s+.*$",
    re.I,
)

# Разделитель только em/en dash (не дефис в фамилии Auger-Aliassime)
_DASH_SPLIT = re.compile(r"\s+[—–]\s+")
_VS_SPLIT = re.compile(r"\s+vs\s+", re.I)


def parse_teams_from_title(title: str) -> tuple[str, str]:
    """Команды из h1: «Georgia — România ponturi…» или «A vs B»."""
    clean = _TITLE_SUFFIX.sub("", (title or "").strip())
    if not clean:
        return "", ""

    if _VS_SPLIT.search(clean):
        parts = _VS_SPLIT.split(clean, maxsplit=1)
        if len(parts) == 2:
            return parts[0].strip(), _trim_away(parts[1])

    if _DASH_SPLIT.search(clean):
        parts = _DASH_SPLIT.split(clean, maxsplit=1)
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
    away = re.sub(r"\s+\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4}.*$", "", away)
    away = re.sub(r",\s+.*$", "", away)
    return away.strip()
