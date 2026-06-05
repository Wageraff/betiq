"""Нормализация названий команд → канонический EN-ключ (хук canonical_team_key)."""
from __future__ import annotations

import re
import unicodedata
from collections import Counter

from src.scraper.utils.team_catalog import ALL_CATALOG, EXTRA_ALIASES

CLUB_PREFIXES = re.compile(r"\b(fc|fk|sc|ac|sk|bk|if|afc|cf|rc)\b", re.I)

_WOMEN_MARKER = re.compile(
    r"\(f\)|\(w\)|\(жен\.?\)|\(ж\.?\)|\(female\)|\(femei\)|\bwomen\b|\(f\.\)",
    re.I,
)

_YOUTH_MARKER = re.compile(
    r"\((\d{1,2})\)|\b(?:U|u)[- ]?(\d{1,2})\b",
)

_WOMEN_KEY_SUFFIX = "women"

_CYRILLIC_MAP = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}

_ARABIC_MAP = {
    "ا": "a", "أ": "a", "إ": "i", "آ": "a", "ب": "b", "ت": "t", "ث": "th",
    "ج": "j", "ح": "h", "خ": "kh", "د": "d", "ذ": "dh", "ر": "r", "ز": "z",
    "س": "s", "ش": "sh", "ص": "s", "ض": "d", "ط": "t", "ظ": "z", "ع": "a",
    "غ": "gh", "ف": "f", "ق": "q", "ك": "k", "ل": "l", "م": "m", "ن": "n",
    "ه": "h", "و": "w", "ي": "y", "ى": "a", "ة": "h", "ئ": "y", "ؤ": "w",
    "ء": "", "لا": "la",
}

_LATIN_FOLD = str.maketrans(
    {
        "ș": "s", "ş": "s", "ț": "t", "ţ": "t", "ă": "a", "â": "a", "î": "i",
        "ë": "e", "é": "e", "è": "e", "ê": "e", "á": "a", "ä": "a", "ö": "o",
        "ü": "u", "ñ": "n",
    }
)

_CANONICAL_DISPLAY: dict[str, str] = {e.key: e.display for e in ALL_CATALOG}
_CATALOG_KEYS: set[str] = set(_CANONICAL_DISPLAY)


def _transliterate_arabic(text: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(text):
        pair = text[i : i + 2]
        if pair in _ARABIC_MAP:
            out.append(_ARABIC_MAP[pair])
            i += 2
            continue
        ch = text[i]
        out.append(_ARABIC_MAP.get(ch, ch))
        i += 1
    return "".join(out)


def _transliterate_cyrillic(text: str) -> str:
    out: list[str] = []
    for ch in text:
        low = ch.lower()
        if "\u0400" <= ch <= "\u04ff" or "\u0500" <= ch <= "\u052f":
            out.append(_CYRILLIC_MAP.get(low, ""))
        else:
            out.append(ch)
    return "".join(out)


def latinize_name(name: str) -> str:
    """Любой алфавит → латиница с пробелами (для display и токенов)."""
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    name = name.translate(_LATIN_FOLD)
    name = _transliterate_cyrillic(name)
    name = _transliterate_arabic(name)
    name = name.replace("—", " ").replace("-", " ")
    return re.sub(r"\s+", " ", name).strip()


def _mechanical_key(name: str) -> str:
    """Любой алфавит → латинский ключ (без алиасов)."""
    name = latinize_name(name).lower()
    name = CLUB_PREFIXES.sub("", name)
    name = re.sub(r"[^a-z0-9]", "", name)
    return name.strip()


def _has_non_latin(text: str) -> bool:
    for ch in text:
        if "\u0400" <= ch <= "\u04ff" or "\u0500" <= ch <= "\u052f":
            return True
        if "\u0600" <= ch <= "\u06ff" or "\u0750" <= ch <= "\u077f":
            return True
    return False


def _sorted_token_key(tokens: list[str]) -> str:
    parts = [t for t in tokens if len(t) >= 2]
    if len(parts) >= 2:
        return "".join(sorted(parts))
    return ""


def _token_key(raw: str) -> str:
    """Игроки/клубы: sorted tokens из латинизированного raw (RU/EN → один ключ)."""
    latin = latinize_name(raw).lower()
    return _sorted_token_key(re.findall(r"[a-z]{2,}", latin))


def _glued_token_key(mechanical: str) -> str:
    """Склеенное имя без пробелов → sorted tokens (felixaugeraliassime → aliassimeaugerfelix)."""
    s = (mechanical or "").lower()
    if len(s) < 10 or re.fullmatch(r"[a-z]+\d{1,2}", s):
        return ""

    n = len(s)
    best: list[str] | None = None
    best_score = -1

    def score(parts: list[str]) -> int:
        if len(parts) < 2 or len(parts) > 6:
            return -1
        if any(len(p) < 2 for p in parts):
            return -1
        total = sum(len(p) for p in parts)
        sc = total * 10 - abs(len(parts) - 3) * 5
        sc -= sum(3 for p in parts if len(p) == 2)
        return sc

    def partition(pos: int, parts: list[str]) -> None:
        nonlocal best, best_score
        if pos == n:
            sc = score(parts)
            if sc > best_score:
                best_score = sc
                best = parts[:]
            return
        if len(parts) >= 6:
            return
        remaining = n - pos
        min_remaining = 2 * max(0, 1 - len(parts))
        if remaining < min_remaining:
            return
        max_len = min(remaining - max(0, min_remaining - 2), 14)
        for length in range(2, max_len + 1):
            parts.append(s[pos : pos + length])
            partition(pos + length, parts)
            parts.pop()

    partition(0, [])
    if not best:
        return ""
    return _sorted_token_key(best)


def _build_team_aliases() -> dict[str, str]:
    """Каталог names + EXTRA → mechanical / token key → canonical key."""
    out = dict(EXTRA_ALIASES)
    for entry in ALL_CATALOG:
        out[entry.key] = entry.key
        for name in entry.names:
            mk = _mechanical_key(name)
            if mk:
                out[mk] = entry.key
            tk = _token_key(name)
            if tk:
                out[tk] = entry.key
    return out


TEAM_ALIASES: dict[str, str] = {}


def _refresh_team_aliases() -> None:
    global TEAM_ALIASES, _COUNTRY_KEYS
    TEAM_ALIASES = _build_team_aliases()
    _COUNTRY_KEYS = set(_CANONICAL_DISPLAY) | set(TEAM_ALIASES.values())


_refresh_team_aliases()
_COUNTRY_KEYS: set[str] = set(_CANONICAL_DISPLAY) | set(TEAM_ALIASES.values())


def resolve_team_key(key: str) -> str:
    """Канонический normalized_key (с учётом алиасов)."""
    k = (key or "").strip().lower()
    if not k:
        return ""
    return TEAM_ALIASES.get(k, k)


def canonical_key_from_names(*names: str) -> str:
    """Один ключ из всех написаний (repair / dedupe). При равенстве — каталог."""
    keys: list[str] = []
    for name in names:
        name = (name or "").strip()
        if not name:
            continue
        k = resolve_team_key(canonical_team_key(name))
        if k:
            keys.append(k)
    if not keys:
        return ""
    counts = Counter(keys)
    best_count = counts.most_common(1)[0][1]
    top = [k for k, c in counts.items() if c == best_count]
    if len(top) == 1:
        return top[0]
    for k in top:
        if k in _CATALOG_KEYS:
            return k
    return min(top, key=len)


def is_catalog_key(key: str) -> bool:
    return resolve_team_key(key) in _CATALOG_KEYS


def format_person_display(name: str) -> str:
    """Felix Auger-Aliassime → Felix Auger Aliassime."""
    name = re.sub(r"\s+", " ", name.replace("-", " ").replace("—", " ").strip())
    if not name:
        return ""
    return " ".join(part.capitalize() for part in name.split())


def is_likely_person_key(key: str) -> bool:
    """Склеенный ключ без пробелов — вероятно теннисист/игрок, не сборная."""
    k = resolve_team_key(key)
    if not k or k in _COUNTRY_KEYS or len(k) < 10:
        return False
    return True


def pick_best_display_raw(candidates: list[str], normalized_key: str) -> str:
    """Лучшее латинское написание из матчей (для display игроков)."""
    key = resolve_team_key(normalized_key)
    valid: list[str] = []
    for name in candidates:
        n = (name or "").strip()
        if n and canonical_team_key(n) == key:
            valid.append(n)
    if not valid:
        return ""
    valid.sort(
        key=lambda n: (not _has_non_latin(n), " " in n, "-" in n, len(n)),
        reverse=True,
    )
    return valid[0]


def legacy_keys_for(canonical_key: str) -> list[str]:
    """Все mechanical-ключи в БД, относящиеся к одной сущности каталога."""
    keys = {canonical_key}
    for old, new in TEAM_ALIASES.items():
        if new == canonical_key:
            keys.add(old)
    return sorted(keys)


def _person_canonical(mechanical: str, raw: str) -> str:
    """Игроки и многословные клубы: sorted tokens + алиасы."""
    if mechanical in _COUNTRY_KEYS or len(mechanical) < 8:
        return mechanical
    if mechanical in TEAM_ALIASES:
        return resolve_team_key(mechanical)

    token_key = _token_key(raw)
    if token_key:
        return resolve_team_key(token_key)

    glued = _glued_token_key(mechanical)
    if glued:
        return resolve_team_key(glued)

    latin = latinize_name(raw).lower()
    tokens = re.findall(r"[a-z]{2,}", latin)
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


def _extract_youth_age(raw: str) -> str | None:
    m = _YOUTH_MARKER.search(raw)
    if not m:
        return None
    return m.group(1) or m.group(2)


def _youth_canonical_key(cleaned: str, age: str) -> str:
    mechanical = _mechanical_key(cleaned)
    if not mechanical:
        return ""
    base = resolve_team_key(mechanical)
    if base in _COUNTRY_KEYS:
        return f"{base}{age}"
    person = resolve_team_key(_person_canonical(mechanical, cleaned))
    if person in _COUNTRY_KEYS:
        return f"{person}{age}"
    return f"{base}{age}"


def canonical_team_key(name: str) -> str:
    """
    Любое написание с любого сайта → один канонический ключ.

    Каталог знает EN/RO/RU/AR/…; неизвестные варианты попадают в aliases при парсинге.
    """
    raw = (name or "").strip()
    if not raw:
        return ""

    women = bool(_WOMEN_MARKER.search(raw))
    youth_age = _extract_youth_age(raw) if not women else None
    cleaned = _WOMEN_MARKER.sub("", raw)
    if youth_age:
        cleaned = _YOUTH_MARKER.sub("", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if youth_age:
        youth_key = _youth_canonical_key(cleaned, youth_age)
        if youth_key:
            return resolve_team_key(youth_key)

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
    return canonical_team_key(name)


def _display_from_raw(key: str, raw: str, *, sport: str | None) -> str:
    """EN display из raw: латиница + Title Case, не кириллица и не склейка ключа."""
    latin = latinize_name(raw)
    if not latin:
        return key.title()
    if sport == "tennis" or is_likely_person_key(key):
        return format_person_display(latin)
    if " " in latin:
        return format_person_display(latin)
    return format_person_display(latin)


def canonical_team_display(
    normalized_key: str,
    *,
    raw_name: str | None = None,
    sport: str | None = None,
) -> str:
    """Справочник и матчи: каталог → EN; иначе латиница с пробелами."""
    key = resolve_team_key(normalized_key)
    if not key:
        return ""

    if key in _CANONICAL_DISPLAY:
        return _CANONICAL_DISPLAY[key]

    raw = (raw_name or "").strip()
    if raw and canonical_team_key(raw) == key:
        return _display_from_raw(key, raw, sport=sport)
    return key.title()


def merge_alias_text(existing: str | None, *names: str) -> str | None:
    """Локальные написания с парсера → aliases (RO/RU/AR/…)."""
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
    """Нужно заменить display на каноническое EN из каталога."""
    display = (display_name or "").strip()
    key = resolve_team_key(normalized_key)
    if not display or not key:
        return False
    if key in _CANONICAL_DISPLAY:
        return display != _CANONICAL_DISPLAY[key]
    if _has_non_latin(display):
        return True
    compact = display.lower().replace(" ", "")
    if compact == key or display == key.title():
        return True
    if (sport == "tennis" or is_likely_person_key(key)) and " " not in display:
        return True
    target = canonical_team_display(key, raw_name=display, sport=sport)
    if display == target:
        return False
    return canonical_team_key(display) == key
