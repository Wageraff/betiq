from src.scraper.proxy_pool import ProxyPool, apply_proxy_geo, build_proxy_url


def test_to_playwright_splits_auth_fields():
    proxy = "http://user_area-RO_session-betiq001:secret@gate.example.com:3120"
    pw = ProxyPool.to_playwright(proxy)
    assert pw == {
        "server": "http://gate.example.com:3120",
        "username": "user_area-RO_session-betiq001",
        "password": "secret",
    }


def test_to_playwright_without_auth():
    proxy = "http://gate.example.com:3120"
    assert ProxyPool.to_playwright(proxy) == {"server": "http://gate.example.com:3120"}


def test_build_proxy_url_substitutes_session_and_geo():
    base = "http://user_area-RO_session-betiq001:secret@gate.example.com:3120"
    url = build_proxy_url(base, "betiq004", "RU")
    assert "session-betiq004" in url
    assert "area-RU" in url
    assert "area-RO" not in url
    assert url.startswith("http://")
    assert "@gate.example.com:3120" in url


def test_apply_proxy_geo_keeps_password():
    proxy = "http://user_area-RO_session-x:pass@host:3120"
    out = apply_proxy_geo(proxy, "GB")
    assert "area-GB" in out
    assert ":pass@host:3120" in out
