from src.scraper.proxy_pool import ProxyPool


def test_to_playwright_embeds_auth_in_server_url():
    proxy = "http://user_area-RO_session-betiq001:secret@gate.example.com:3120"
    pw = ProxyPool.to_playwright(proxy)
    assert pw is not None
    assert set(pw) == {"server"}
    assert pw["server"] == (
        "http://user_area-RO_session-betiq001:secret@gate.example.com:3120"
    )


def test_to_playwright_without_auth():
    proxy = "http://gate.example.com:3120"
    assert ProxyPool.to_playwright(proxy) == {"server": "http://gate.example.com:3120"}
