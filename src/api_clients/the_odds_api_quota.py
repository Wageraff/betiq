"""Circuit breaker: не дергать The Odds API после 401/429."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from src.config import settings

log = logging.getLogger("the_odds_api")

_suspended_until: datetime | None = None
_last_warn_at: datetime | None = None


def is_quota_suspended() -> bool:
    if _suspended_until is None:
        return False
    if datetime.now(timezone.utc) >= _suspended_until:
        return False
    return True


def suspended_until() -> datetime | None:
    return _suspended_until


def note_quota_exhausted(status_code: int) -> None:
    """Приостановить запросы на odds_quota_cooldown_minutes."""
    global _suspended_until, _last_warn_at

    cooldown = max(1, settings.odds_quota_cooldown_minutes)
    until = datetime.now(timezone.utc) + timedelta(minutes=cooldown)
    if _suspended_until is None or until > _suspended_until:
        _suspended_until = until

    now = datetime.now(timezone.utc)
    if _last_warn_at is None or (now - _last_warn_at).total_seconds() >= 3600:
        _last_warn_at = now
        log.warning(
            "The Odds API quota exhausted (HTTP %s), suspended until %s",
            status_code,
            _suspended_until.isoformat(),
        )


def reset_quota_suspend() -> None:
    """Для тестов и ручного сброса."""
    global _suspended_until, _last_warn_at
    _suspended_until = None
    _last_warn_at = None
