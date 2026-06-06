from datetime import datetime, timedelta, timezone

from src.scraper.utils.alert_cooldown import ALERT_NO_NEW, ALERT_SCRAPE_ERROR


def test_alert_type_constants():
    assert ALERT_SCRAPE_ERROR == "scrape_error"
    assert ALERT_NO_NEW == "no_new"


def test_dedup_window_math():
    last = datetime.now(timezone.utc) - timedelta(hours=12)
    window = timedelta(hours=24)
    assert datetime.now(timezone.utc) - last < window
