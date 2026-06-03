"""Singleton Playwright: stealth, proxy, Cloudflare-паузы (паттерны из reference_scraper)."""
from __future__ import annotations

import logging
import random
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional, Tuple

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from src.config import USER_AGENTS, settings

try:
    from playwright_stealth import stealth_async

    HAS_STEALTH = True
except Exception:
    HAS_STEALTH = False

from src.scraper.proxy_pool import ProxyPool

log = logging.getLogger("browser")

_PROXY_ERRORS = ("ERR_CERT", "ERR_CONNECTION", "ERR_PROXY", "ERR_TUNNEL", "net::")

_playwright: Optional[Playwright] = None
_browser: Optional[Browser] = None
_proxy_pool = ProxyPool()


def ensure_proxy_configured() -> None:
    if settings.require_proxy and not _proxy_pool.has_proxies:
        raise RuntimeError("Proxies required but proxies.txt is empty")


def is_proxy_error(exc: BaseException) -> bool:
    msg = str(exc)
    return any(x in msg for x in _PROXY_ERRORS)


def report_proxy_failure(exc: BaseException, proxy: Optional[str]) -> None:
    if proxy and is_proxy_error(exc):
        _proxy_pool.report_failure(proxy)


async def wait_cloudflare(page: Page, base_ms: int = 3000) -> None:
    title = (await page.title()) or ""
    lower = title.lower()
    if "just a moment" in lower or "attention required" in lower:
        log.info("Cloudflare challenge detected, waiting 10s")
        await page.wait_for_timeout(10_000)
    await page.wait_for_timeout(random.randint(base_ms, base_ms + 2000))


async def _launch_browser() -> Tuple[Browser, Optional[str]]:
    proxy = _proxy_pool.get()
    if settings.require_proxy and not proxy:
        raise RuntimeError("No available proxies")

    launch_args = {
        "headless": settings.headless,
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ],
    }
    pw_proxy = ProxyPool.to_playwright(proxy)
    if pw_proxy:
        launch_args["proxy"] = pw_proxy

    global _playwright, _browser
    if _playwright is None:
        _playwright = await async_playwright().start()
    if _browser is None:
        _browser = await _playwright.chromium.launch(**launch_args)
    return _browser, proxy


async def new_context() -> Tuple[BrowserContext, Optional[str]]:
    browser, proxy = await _launch_browser()
    user_agent = random.choice(USER_AGENTS)
    context = await browser.new_context(
        user_agent=user_agent,
        viewport={"width": settings.viewport_width, "height": settings.viewport_height},
        locale="en-US",
        timezone_id="Europe/London",
        ignore_https_errors=True,
    )
    return context, proxy


async def new_page() -> Tuple[Page, BrowserContext, Optional[str]]:
    context, proxy = await new_context()
    page = await context.new_page()
    if HAS_STEALTH:
        try:
            await stealth_async(page)
        except Exception as e:
            log.debug("stealth: %s", e)
    return page, context, proxy


@asynccontextmanager
async def page_session() -> AsyncIterator[Tuple[Page, Optional[str]]]:
    """Контекст страницы: закрывает context после использования."""
    page, context, proxy = await new_page()
    try:
        yield page, proxy
    finally:
        await context.close()


async def shutdown() -> None:
    global _playwright, _browser
    if _browser is not None:
        await _browser.close()
        _browser = None
    if _playwright is not None:
        await _playwright.stop()
        _playwright = None


@asynccontextmanager
async def browser_lifecycle() -> AsyncIterator[None]:
    try:
        yield
    finally:
        await shutdown()
