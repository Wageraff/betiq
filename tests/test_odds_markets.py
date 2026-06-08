from src.api_clients.odds_markets import (
    allowed_api_football_markets,
    allowed_the_odds_api_markets,
    is_allowed_api_football_market,
    is_allowed_the_odds_market,
)


def test_the_odds_allowed_from_defaults():
    allowed = allowed_the_odds_api_markets()
    assert is_allowed_the_odds_market("h2h", allowed)
    assert is_allowed_the_odds_market("totals", allowed)
    assert is_allowed_the_odds_market("btts", allowed)
    assert not is_allowed_the_odds_market("alternate_spreads", allowed)


def test_api_football_derived_from_the_odds_config():
    allowed = allowed_api_football_markets()
    assert is_allowed_api_football_market("Match Winner", allowed)
    assert is_allowed_api_football_market("Goals Over/Under", allowed)
    assert is_allowed_api_football_market("Both Teams Score", allowed)
    assert not is_allowed_api_football_market("First Goal Scorer", allowed)
