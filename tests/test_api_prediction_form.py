from src.api_clients.stats_sync import _normalize_form


def test_normalize_form_takes_last_ten_wdl():
    raw = "DWDLLWWDWDWWWWLDWLLWDLLWWWWDWLWWLWLWWWDLLWD"
    assert _normalize_form(raw) == "LWLWWWDLLWD"


def test_normalize_form_short_passthrough():
    assert _normalize_form("WWDL") == "WWDL"
