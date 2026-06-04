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
