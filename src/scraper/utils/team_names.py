"""Нормализация названий команд → канонический EN-ключ (хук canonical_team_key)."""
from __future__ import annotations

import re
import unicodedata

from src.scraper.utils.team_aliases import TEAM_ALIASES

CLUB_PREFIXES = re.compile(r"\b(fc|fk|sc|ac|sk|bk|if|afc|cf|rc)\b", re.I)

_WOMEN_MARKER = re.compile(
    r"\(f\)|\(w\)|\(жен\.?\)|\(ж\.?\)|\(female\)|\(femei\)|\bwomen\b|\(f\.\)",
    re.I,
)

_WOMEN_KEY_SUFFIX = "women"

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
    "newzealand": "New Zealand",
    "algeria": "Algeria",
    "poland": "Poland",
    "luxembourg": "Luxembourg",
    "tunisia": "Tunisia",
    "nigeria": "Nigeria",
    "mexico": "Mexico",
    "colombia": "Colombia",
    "serbia": "Serbia",
    "syria": "Syria",
    "greece": "Greece",
    "sweden": "Sweden",
    "belarus": "Belarus",
    "tajikistan": "Tajikistan",
    "india": "India",
    "iraq": "Iraq",
    "czechia": "Czechia",
    "guatemala": "Guatemala",
    "cyprus": "Cyprus",
    "guinea": "Guinea",
    "northernireland": "Northern Ireland",
    "andorra": "Andorra",
    "liechtenstein": "Liechtenstein",
    "slovakia": "Slovakia",
    "slovenia": "Slovenia",
    "montenegro": "Montenegro",
    "hungary": "Hungary",
    "finland": "Finland",
    "norway": "Norway",
    "morocco": "Morocco",
    "egypt": "Egypt",
    "switzerland": "Switzerland",
    "turkey": "Turkey",
    "usa": "USA",
    "jordan": "Jordan",
    "chile": "Chile",
    "canada": "Canada",
    "venezuela": "Venezuela",
    "australia": "Australia",
    "ireland": "Ireland",
    "uzbekistan": "Uzbekistan",
    "wales": "Wales",
    "moldova": "Moldova",
    "bulgaria": "Bulgaria",
    "brazilwomen": "Brazil (W)",
    "dominicanwomen": "Dominican Republic (W)",
    "turkeywomen": "Turkey (W)",
    "netherlandswomen": "Netherlands (W)",
    "cska": "CSKA",
    "unics": "UNICS",
    "indianafever": "Indiana Fever",
    "atlantadream": "Atlanta Dream",
}


def resolve_team_key(key: str) -> str:
    """Канонический normalized_key (с учётом алиасов)."""
    k = (key or "").strip().lower()
    if not k:
        return ""
    return TEAM_ALIASES.get(k, k)


_COUNTRY_KEYS: set[str] = set(_CANONICAL_DISPLAY) | set(TEAM_ALIASES.values())


def is_likely_person_key(key: str) -> bool:
    """Склеенный ключ без пробелов — вероятно теннисист/игрок, не сборная."""
    k = resolve_team_key(key)
    if not k or k in _COUNTRY_KEYS or len(k) < 10:
        return False
    return True


def format_person_display(name: str) -> str:
    """Felix Auger-Aliassime → Felix Auger Aliassime."""
    name = re.sub(r"\s+", " ", name.replace("-", " ").replace("—", " ").strip())
    if not name:
        return ""
    return " ".join(part.capitalize() for part in name.split())


def pick_best_display_raw(candidates: list[str], normalized_key: str) -> str:
    """Лучшее написание из матчей/парсера для display_name."""
    key = resolve_team_key(normalized_key)
    valid: list[str] = []
    for name in candidates:
        n = (name or "").strip()
        if n and canonical_team_key(n) == key:
            valid.append(n)
    if not valid:
        return ""
    valid.sort(
        key=lambda n: (
            " " in n,
            "-" in n,
            len(n),
        ),
        reverse=True,
    )
    return valid[0]


def legacy_keys_for(canonical_key: str) -> list[str]:
    """Все ключи в БД, которые относятся к одной команде."""
    keys = {canonical_key}
    for old, new in TEAM_ALIASES.items():
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


def _mechanical_key(name: str) -> str:
    """Транслит + снятие диакритики, без алиасов."""
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    name = name.translate(_LATIN_FOLD)
    name = _transliterate_cyrillic(name)
    name = name.lower()
    name = CLUB_PREFIXES.sub("", name)
    name = re.sub(r"[^a-z0-9]", "", name)
    return name.strip()


def _person_canonical(mechanical: str, raw: str) -> str:
    """
    Теннисисты: «Matteo Arnaldi» и «Арнальди М.» → один ключ (sorted tokens / alias).
    """
    if mechanical in _COUNTRY_KEYS or len(mechanical) < 8:
        return mechanical
    if mechanical in TEAM_ALIASES:
        return resolve_team_key(mechanical)

    tokens = re.findall(r"[a-z]{2,}", raw.lower().replace("—", " "))
    tokens = [_transliterate_cyrillic(t) for t in tokens]
    tokens = [re.sub(r"[^a-z]", "", t) for t in tokens if t]
    tokens = [t for t in tokens if len(t) > 1]

    if len(tokens) >= 2:
        return "".join(sorted(tokens))

    if len(tokens) == 1 and len(mechanical) > len(tokens[0]):
        suffix = mechanical[len(tokens[0]) :]
        if len(suffix) == 1:
            return mechanical

    return mechanical


def _strip_women_suffix(key: str) -> str:
    if key.endswith(_WOMEN_KEY_SUFFIX):
        return key[: -len(_WOMEN_KEY_SUFFIX)]
    return key


def _resolve_country_base(mechanical: str, cleaned: str) -> str:
    """Ключ сборной/клуба без суффикса women."""
    if mechanical in TEAM_ALIASES:
        return _strip_women_suffix(resolve_team_key(mechanical))

    key = resolve_team_key(_person_canonical(mechanical, cleaned))
    if key in _COUNTRY_KEYS:
        return _strip_women_suffix(key)
    return _strip_women_suffix(key)


def _apply_women_suffix(base: str) -> str:
    base = _strip_women_suffix(base)
    if not base:
        return ""
    return f"{base}{_WOMEN_KEY_SUFFIX}"


def canonical_team_key(name: str) -> str:
    """
    Хук: любое написание с сайта → один канонический ключ (англ./латиница).

    Используется для match_key, справочника teams и слияния дубликатов.
    """
    raw = (name or "").strip()
    if not raw:
        return ""

    women = bool(_WOMEN_MARKER.search(raw))
    cleaned = _WOMEN_MARKER.sub("", raw)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    mechanical = _mechanical_key(cleaned)
    if not mechanical:
        return ""

    if women:
        base = _resolve_country_base(mechanical, cleaned)
        if base in _COUNTRY_KEYS or len(base) >= 4:
            return _apply_women_suffix(base)
        return _apply_women_suffix(resolve_team_key(mechanical))

    key = resolve_team_key(mechanical)
    if key in _COUNTRY_KEYS:
        return key
    return resolve_team_key(_person_canonical(mechanical, cleaned))


def normalize_team_name(name: str) -> str:
    """Алиас для match_key / dedupe — всегда канонический ключ."""
    return canonical_team_key(name)


def canonical_team_display(
    normalized_key: str,
    *,
    raw_name: str | None = None,
    sport: str | None = None,
) -> str:
    """Имя для справочника: сборные — EN; игроки — с пробелами."""
    key = resolve_team_key(normalized_key)
    if not key:
        return ""
    raw = (raw_name or "").strip()
    if raw and canonical_team_key(raw) == key:
        if sport == "tennis" or is_likely_person_key(key) or " " in raw or "-" in raw:
            return format_person_display(raw)
        return raw
    if key in _CANONICAL_DISPLAY:
        return _CANONICAL_DISPLAY[key]
    if sport == "tennis" or is_likely_person_key(key):
        return format_person_display(raw) if raw else key.title()
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


def is_catalog_display_name(
    display_name: str,
    normalized_key: str,
    *,
    sport: str | None = None,
) -> bool:
    """Можно заменить display_name на каноническое (с парсера или матчей)."""
    display = (display_name or "").strip()
    key = resolve_team_key(normalized_key)
    if not display or not key:
        return False
    if (sport == "tennis" or is_likely_person_key(key)) and " " not in display:
        return True
    target = canonical_team_display(key, raw_name=display, sport=sport)
    if display == target:
        return False
    return canonical_team_key(display) == key
