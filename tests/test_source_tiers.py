from src.scraper.source_stats import SourceStatsRow
from src.scraper.source_tiers import ScrapeTier, include_in_quick, tier_for_module


def test_tier_mapping():
    assert tier_for_module("vseprosport_ru") == ScrapeTier.HIGH
    assert tier_for_module("beturi") == ScrapeTier.LOW
    assert tier_for_module("legalbet_ru") == ScrapeTier.MEDIUM
    assert include_in_quick("beturi") is False
    assert include_in_quick("stavkiprognozy_ru") is True


def test_health_scoring():
    ok = SourceStatsRow(1, runs=10, items_saved=8, errors=0, empty_runs=2, None, None)
    assert ok.health == "ok"

    warn = SourceStatsRow(1, runs=10, items_saved=1, errors=1, empty_runs=8, None, None)
    assert warn.health == "warn"

    err = SourceStatsRow(1, runs=10, items_saved=0, errors=4, empty_runs=6, None, None)
    assert err.health == "error"

    idle = SourceStatsRow(1, runs=0, items_saved=0, errors=0, empty_runs=0, None, None)
    assert idle.health == "idle"
