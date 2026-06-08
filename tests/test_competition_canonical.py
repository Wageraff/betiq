from src.scraper.utils.normalizer import (
    canonical_competition_name,
    competition_needs_canonicalization,
)


def test_chm_to_world_cup():
    assert canonical_competition_name("ЧМ-2026") == "World Cup"
    assert competition_needs_canonicalization("ЧМ-2026")


def test_nhl_cyrillic():
    assert canonical_competition_name("НХЛ") == "NHL"


def test_world_cup_unchanged():
    assert not competition_needs_canonicalization("World Cup")
