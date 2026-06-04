"""Нормализация названий команд (без зависимости от БД)."""
from __future__ import annotations

import re
import unicodedata

CLUB_PREFIXES = re.compile(r"\b(fc|fk|sc|ac|sk|bk|if|afc|cf|rc)\b", re.I)

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

# RO/RU/варианты без диакритики → канонический ключ (англ.)
_TEAM_ALIASES: dict[str, str] = {
    "frana": "france",
    "franta": "france",
    "frantsiya": "france",
    "franciya": "france",
    "coastadefildes": "ivorycoast",
    "coastadefilde": "ivorycoast",
    "coastadefildei": "ivorycoast",
    "kotdivuar": "ivorycoast",
    "kotdivoire": "ivorycoast",
    "cotedivoire": "ivorycoast",
    "anglia": "england",
    "olanda": "netherlands",
    "danemarca": "denmark",
    "nouazeelanda": "newzealand",
    "alger": "algeria",
    "belgia": "belgium",
    "polonia": "poland",
    "luxemburg": "luxembourg",
    "italia": "italy",
    "tunisia": "tunisia",
    "honduras": "honduras",
    "argentina": "argentina",
    "nigeria": "nigeria",
}

# Диакритика, которая не всегда в категории Mn (ș, ț и т.д.)
_LATIN_FOLD = str.maketrans(
    {
        "ș": "s",
        "ş": "s",
        "ț": "t",
        "ţ": "t",
        "ă": "a",
        "â": "a",
        "î": "i",
        "ë": "e",
        "é": "e",
        "è": "e",
        "ê": "e",
        "á": "a",
        "ä": "a",
        "ö": "o",
        "ü": "u",
        "ñ": "n",
    }
)

# Канонические английские названия для справочника (ключ = normalized_key).
_CANONICAL_DISPLAY: dict[str, str] = {
    "france": "France",
    "ivorycoast": "Ivory Coast",
    "denmark": "Denmark",
    "drcongo": "DR Congo",
    "congo": "Congo",
    "england": "England",
    "germany": "Germany",
    "spain": "Spain",
    "italy": "Italy",
    "romania": "Romania",
    "russia": "Russia",
    "ukraine": "Ukraine",
    "portugal": "Portugal",
    "netherlands": "Netherlands",
    "belgium": "Belgium",
    "brazil": "Brazil",
    "argentina": "Argentina",
    "honduras": "Honduras",
    "england": "England",
    "newzealand": "New Zealand",
    "algeria": "Algeria",
    "poland": "Poland",
    "luxembourg": "Luxembourg",
    "tunisia": "Tunisia",
    "nigeria": "Nigeria",
}


def resolve_team_key(key: str) -> str:
    """Канонический normalized_key (с учётом алиасов)."""
    k = (key or "").strip().lower()
    if not k:
        return ""
    return _TEAM_ALIASES.get(k, k)


def legacy_keys_for(canonical_key: str) -> list[str]:
    """Все ключи в БД, которые относятся к одной команде."""
    keys = {canonical_key}
    for old, new in _TEAM_ALIASES.items():
        if new == canonical_key:
            keys.add(old)
    return sorted(keys)


def _transliterate_cyrillic(text: str) -> str:
    out: list[str] = []
    for ch in text:
        low = ch.lower()
        if "\u0400" <= ch <= "\u04ff" or "\u0500" <= ch <= "\u052f":
            out.append(_CYRILLIC_MAP.get(low, ""))
        else:
            out.append(ch)
    return "".join(out)


def canonical_team_display(normalized_key: str, *, raw_name: str | None = None) -> str:
    """Английское имя для справочника teams.display_name."""
    key = resolve_team_key(normalized_key)
    if not key:
        return ""
    raw = (raw_name or "").strip()
    if raw and " " in raw and normalize_team_name(raw) == key:
        return raw
    if key in _CANONICAL_DISPLAY:
        return _CANONICAL_DISPLAY[key]
    return key.title()


def merge_alias_text(existing: str | None, *names: str) -> str | None:
    """Добавить варианты написания (RO/RU/с сайта) в aliases, без дублей."""
    seen: set[str] = set()
    parts: list[str] = []
    for block in (existing,):
        if block:
            for item in block.split(","):
                item = item.strip()
                if item and item.lower() not in seen:
                    seen.add(item.lower())
                    parts.append(item)
    for name in names:
        name = (name or "").strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        parts.append(name)
    return ", ".join(parts) if parts else None


def is_catalog_display_name(display_name: str, normalized_key: str) -> bool:
    """Имя из справочника (EN) или ещё «сырое» с парсера — можно обновить на canonical."""
    display = (display_name or "").strip()
    key = resolve_team_key(normalized_key)
    if not display or not key:
        return False
    if display == canonical_team_display(key):
        return True
    return resolve_team_key(normalize_team_name(display)) == key


def normalize_team_name(name: str) -> str:
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    name = name.translate(_LATIN_FOLD)
    name = _transliterate_cyrillic(name)
    name = name.lower()
    name = CLUB_PREFIXES.sub("", name)
    name = re.sub(r"[^a-z0-9]", "", name)
    name = name.strip()
    return _TEAM_ALIASES.get(name, name)
