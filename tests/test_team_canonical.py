"""Канонические ключи команд (хук canonical_team_key)."""
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.scraper.utils.match_key_build import build_match_key
from src.scraper.utils.team_names import canonical_team_display, canonical_team_key


class TeamCanonicalTests(unittest.TestCase):
    def test_russia_variants(self) -> None:
        for name in ("Rusia", "Rossiya", "Россия", "Russia"):
            self.assertEqual(canonical_team_key(name), "russia")

    def test_mexico_variants(self) -> None:
        for name in ("Mexic", "Meksika", "Мексика", "Mexico"):
            self.assertEqual(canonical_team_key(name), "mexico")

    def test_spain_iraq_syria(self) -> None:
        self.assertEqual(canonical_team_key("Spania"), "spain")
        self.assertEqual(canonical_team_key("Испания"), "spain")
        self.assertEqual(canonical_team_key("Irak"), "iraq")
        self.assertEqual(canonical_team_key("Siriya"), "syria")

    def test_same_match_key_russia_burkina(self) -> None:
        day = date(2026, 6, 5)
        k1 = build_match_key("Rusia", "Burkina Faso", day)
        k2 = build_match_key("Rossiya", "Burkina Faso", day)
        self.assertEqual(k1, k2)

    def test_france_ivory(self) -> None:
        day = date(2026, 6, 4)
        keys = {
            build_match_key(h, a, day)
            for h, a in (
                ("Franta", "Coasta de Fildes"),
                ("Франция", "Кот-д'Ивуар"),
                ("France", "Ivory Coast"),
            )
        }
        self.assertEqual(len(keys), 1)

    def test_tennis_arnaldi(self) -> None:
        self.assertEqual(
            canonical_team_key("Matteo Arnaldi"),
            canonical_team_key("Арнальди М."),
        )

    def test_cyrillic_clubs_and_players(self) -> None:
        from src.scraper.utils.team_names import canonical_team_display

        self.assertEqual(
            canonical_team_key("Ребека Масарова"),
            canonical_team_key("Rebeka Masarova"),
        )
        self.assertEqual(canonical_team_display("masarovarebeka"), "Rebeka Masarova")
        self.assertEqual(
            canonical_team_key("Сан-Антонио Сперз"),
            canonical_team_key("San Antonio Spurs"),
        )
        self.assertEqual(
            canonical_team_display("antoniosanspurs"),
            "San Antonio Spurs",
        )
        self.assertEqual(
            canonical_team_key("Расинг Клуб Монтевидео"),
            canonical_team_key("Racing Club Montevideo"),
        )
        self.assertEqual(
            canonical_team_display("clubmontevideoracing"),
            "Racing Club Montevideo",
        )

    def test_arabic_catalog(self) -> None:
        self.assertEqual(canonical_team_key("إنجلترا"), "england")
        self.assertEqual(canonical_team_key("فرنسا"), "france")
        self.assertEqual(canonical_team_display("england"), "England")

    def test_england_new_zealand_ru_ro(self) -> None:
        for name, key in (
            ("Англия", "england"),
            ("Anglia", "england"),
            ("Новая Зеландия", "newzealand"),
            ("Noua Zeelanda", "newzealand"),
            ("Австралия", "australia"),
            ("Швейцария", "switzerland"),
            ("США", "usa"),
            ("SUA", "usa"),
            ("Германия", "germany"),
            ("Армения", "armenia"),
            ("Казахстан", "kazakhstan"),
        ):
            self.assertEqual(canonical_team_key(name), key, msg=name)

    def test_same_match_key_england_nz(self) -> None:
        day = date(2026, 6, 6)
        k1 = build_match_key("Англия", "Новая Зеландия", day)
        k2 = build_match_key("Anglia", "Noua Zeelanda", day)
        self.assertEqual(k1, k2)

    def test_women_volleyball_brazil_dominican(self) -> None:
        day = date(2026, 6, 5)
        k_ru = build_match_key("Бразилия (жен.)", "Доминикана (жен.)", day)
        k_ro = build_match_key("Braziliei (F)", "Republicii Dominicane (F)", day)
        self.assertEqual(k_ru, k_ro)
        self.assertEqual(canonical_team_key("Бразилия (жен.)"), "brazilwomen")
        self.assertEqual(canonical_team_key("Republicii Dominicane (F)"), "dominicanwomen")

    def test_glued_name_same_key(self) -> None:
        self.assertEqual(
            canonical_team_key("Felix Auger-Aliassime"),
            canonical_team_key("felixaugeraliassime"),
        )

    def test_youth_teams(self) -> None:
        self.assertEqual(canonical_team_key("Ирак (23)"), "iraq23")
        self.assertEqual(canonical_team_key("Irak (23)"), "iraq23")
        self.assertEqual(canonical_team_key("Казахстан (19)"), "kazakhstan19")
        self.assertEqual(canonical_team_display("iraq23"), "Iraq (23)")

    def test_women_display_catalog(self) -> None:
        self.assertEqual(canonical_team_display("belgiumwomen"), "Belgium (W)")
        self.assertEqual(canonical_team_key("Бельгия (жен)"), "belgiumwomen")

    def test_knicks_and_spurs(self) -> None:
        self.assertEqual(canonical_team_key("Нью-Йорк Никс"), "knicksnewyork")
        self.assertEqual(canonical_team_display("knicksnewyork"), "New York Knicks")
        self.assertEqual(canonical_team_key("Сан-Антонио"), "antoniosanspurs")

    def test_get_or_create_display_from_raw(self) -> None:
        from src.scraper.utils.team_names import canonical_team_display

        key = canonical_team_key("Алехандро Моро Каньяс")
        display = canonical_team_display(key, raw_name="Алехандро Моро Каньяс", sport="tennis")
        self.assertEqual(display, "Alejandro Moro Cañas")
        self.assertNotIn("Alehandro", display)

    def test_canonical_key_from_names_merges_glued(self) -> None:
        from src.scraper.utils.team_names import canonical_key_from_names

        key = canonical_key_from_names(
            "felixaugeraliassime",
            "Felix Auger-Aliassime",
            "Felix Auger Aliassime",
        )
        self.assertEqual(key, "aliassimeaugerfelix")


if __name__ == "__main__":
    unittest.main()
