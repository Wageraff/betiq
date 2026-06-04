#!/usr/bin/env python3
"""
Проверка склейки матча Франция — Кот-д'Ивуар с четырёх источников.
Запуск: PYTHONPATH=. python scripts/verify_france_ivory_grouping.py
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.scraper.utils.match_key_build import build_match_key
from src.scraper.utils.team_names import canonical_team_key

# Имена команд, как их отдают сайты (curl / парсеры)
CASES = [
    ("legalbet.ro", "Franta", "Coasta de Fildes"),
    ("beturi.ro", "Franța", "Coasta de Fildeș"),
    ("legalbet.ru", "Франция", "Кот-д'Ивуар"),
    ("pontul-zilei.com", "Franța", "Coasta de Fildeș"),
]

MATCH_DAY = date(2026, 6, 4)


def main() -> None:
    keys: set[str] = set()
    print(f"Дата матча для ключа: {MATCH_DAY}\n")
    for source, home, away in CASES:
        key = build_match_key(home, away, MATCH_DAY)
        keys.add(key)
        print(f"{source:20} {home!r:22} vs {away!r:22}")
        print(f"  norm: {canonical_team_key(home):12} : {canonical_team_key(away)}")
        print(f"  key:  {key}\n")

    if len(keys) == 1:
        print("OK: все источники дают один match_key — прогнозы попадут в один матч.")
    else:
        print(f"FAIL: получено {len(keys)} разных ключей — нужны доработки normalize/aliases.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
