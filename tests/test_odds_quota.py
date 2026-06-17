"""Tests for The Odds API quota savings helpers."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.api_clients.odds_scope import (
    match_odds_recently_fetched,
    match_within_event_odds_window,
)
from src.api_clients.the_odds_api_quota import (
    is_quota_suspended,
    note_quota_exhausted,
    reset_quota_suspend,
)
from src.config import settings
from src.db.models import Match


def _match(*, hours_ahead: float, fetched_min_ago: float | None = None) -> Match:
    now = datetime.now(timezone.utc)
    m = Match(
        id=1,
        team_home="A",
        team_away="B",
        sport="football",
        match_date=now + timedelta(hours=hours_ahead),
    )
    if fetched_min_ago is not None:
        m.odds_fetched_at = now - timedelta(minutes=fetched_min_ago)
    return m


def test_event_window_48h():
    assert match_within_event_odds_window(_match(hours_ahead=24)) is True
    assert match_within_event_odds_window(_match(hours_ahead=72)) is False
    assert match_within_event_odds_window(_match(hours_ahead=-1)) is False


def test_skip_fresh_odds():
    skip = settings.odds_fresh_skip_minutes
    assert match_odds_recently_fetched(_match(hours_ahead=1, fetched_min_ago=5)) is True
    assert (
        match_odds_recently_fetched(
            _match(hours_ahead=1, fetched_min_ago=skip + 5)
        )
        is False
    )
    assert match_odds_recently_fetched(_match(hours_ahead=1)) is False


def test_quota_circuit_breaker():
    reset_quota_suspend()
    assert is_quota_suspended() is False
    note_quota_exhausted(401)
    assert is_quota_suspended() is True
    reset_quota_suspend()
