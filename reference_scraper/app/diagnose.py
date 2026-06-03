"""Проверка прокси и доступа к сайту."""
import asyncio
import random
import logging

from playwright.async_api import async_playwright

try:
    from playwright_stealth import stealth_async
    HAS_STEALTH = True
except Exception:
    HAS_STEALTH = False

from .settings import (
    DIAGNOSE_TEST_URL, URLS_FILE, HEADLESS, PAGE_TIMEOUT,
    VIEWPORT_WIDTH, VIEWPORT_HEIGHT, USER_AGENTS, setup_logging,
)
from .proxy_pool import ProxyPool
from .url_list import load_urls

log = logging.getLogger("diagnose")


def get_test_url() -> str:
    urls = load_urls(URLS_FILE)
    return urls[0] if urls else DIAGNOSE_TEST_URL


async def check(playwright, url: str, use_proxy: bool):
    pool = ProxyPool()
    proxy = pool.get() if use_proxy else None
    label = "С ПРОКСИ" if proxy else "БЕЗ ПРОКСИ"
    print(f"\n{'='*50}\n  {label}: {url}\n{'='*50}")

    launch = {"headless": HEADLESS, "args": ["--no-sandbox"]}
    if proxy:
        launch["proxy"] = ProxyPool.to_playwright(proxy)

    browser = await playwright.chromium.launch(**launch)
    ctx = await browser.new_context(
        user_agent=random.choice(USER_AGENTS),
        viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
        locale="ru-RU",
        ignore_https_errors=True,
    )
    page = await ctx.new_page()
    if HAS_STEALTH:
        try:
            await stealth_async(page)
        except Exception:
            pass
    try:
        r = await page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
        await page.wait_for_timeout(3000)
        title = await page.title()
        h1 = await page.evaluate("() => document.querySelector('h1')?.innerText || ''")
        print(f"  HTTP: {r.status if r else '?'}")
        print(f"  Title: {title[:80]}")
        print(f"  H1: {h1[:80]}")
        ok = bool(h1 or (title and "moment" not in title.lower()))
        print("  ✅ OK" if ok else "  ❌ Провал")
        return ok
    finally:
        await ctx.close()
        await browser.close()


async def run_async():
    setup_logging()
    url = get_test_url()
    async with async_playwright() as p:
        await check(p, url, False)
        if ProxyPool().has_proxies:
            await check(p, url, True)


def main():
    asyncio.run(run_async())


if __name__ == "__main__":
    main()
