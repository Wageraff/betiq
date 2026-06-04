"""Singleton Playwright: stealth, proxy по geo, проверка перед парсингом."""
from __future__ import annotations

import logging
import random
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import AsyncIterator, Optional, Tuple

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    Route,
    async_playwright,
)

from src.config import USER_AGENTS, settings

try:
    from playwright_stealth import stealth_async

    HAS_STEALTH = True
except Exception:
    HAS_STEALTH = False

from src.scraper.proxy_pool import ProxyPool
from src.scraper.utils.match_datetime import GEO_SOURCE_TZ

log = logging.getLogger("browser")

_PROXY_ERRORS = ("ERR_CERT", "ERR_CONNECTION", "ERR_PROXY", "ERR_TUNNEL", "net::")

_playwright: Optional[Playwright] = None
_browser: Optional[Browser] = None
_proxy_pool = ProxyPool()

_geo_ctx: ContextVar[Optional[str]] = ContextVar("scraper_proxy_geo", default=None)

_BLOCKED_RESOURCE_TYPES = frozenset({"image", "font", "media", "stylesheet"})

_AD_URL_MARKERS = (
    "doubleclick.net",
    "googlesyndication.com",
    "google-analytics.com",
    "googletagmanager.com",
    "googleadservices.com",
    "facebook.net/tr",
    "adservice.google",
    "/ads/",
    "/ad/",
    "banner",
    "taboola.com",
    "outbrain.com",
    "criteo.com",
    "hotjar.com",
    "clarity.ms",
    "mc.yandex",
    "an.yandex.ru",
    "metrika.yandex",
    "adfox.ru",
    "begun.ru",
    "mail.ru/ads",
    "adsystem",
    "adriver.ru",
    "relap.io",
    "smi2.ru",
    "mediametrics",
)

GEO_LOCALE: dict[str, str] = {
    "RO": "ro-RO",
    "RU": "ru-RU",
    "GB": "en-GB",
    "UK": "en-GB",
    "DE": "de-DE",
}


def ensure_proxy_configured() -> None:
    if settings.require_proxy and not _proxy_pool.has_proxies:
        raise RuntimeError("Proxies required but proxies.txt is empty")


def is_proxy_error(exc: BaseException) -> bool:
    msg = str(exc)
    return any(x in msg for x in _PROXY_ERRORS)


def report_proxy_failure(exc: BaseException, proxy: Optional[str]) -> None:
    if proxy and is_proxy_error(exc):
        _proxy_pool.report_failure(proxy)


def _resolve_geo(geo: Optional[str]) -> Optional[str]:
    if geo:
        return geo.strip().upper()
    return _geo_ctx.get()


def _browser_locale(geo: Optional[str]) -> str:
    if geo and geo.upper() in GEO_LOCALE:
        return GEO_LOCALE[geo.upper()]
    return "en-US"


def _browser_timezone(geo: Optional[str]) -> str:
    if geo and geo.upper() in GEO_SOURCE_TZ:
        return GEO_SOURCE_TZ[geo.upper()]
    return settings.match_datetime_source_tz


def _proxy_geo_candidates(geo: Optional[str]) -> list[Optional[str]]:
    """Порядок: geo источника → fallback из config (по умолчанию GB)."""
    out: list[Optional[str]] = []
    if geo:
        out.append(geo.upper())
    fallback = (settings.proxy_fallback_geo or "GB").strip().upper()
    if fallback and fallback not in out:
        out.append(fallback)
    if not out:
        out.append(None)
    return out


@asynccontextmanager
async def scrape_geo_context(geo: Optional[str]) -> AsyncIterator[None]:
    """Задаёт geo для вложенных page_session() без явного параметра."""
    token = _geo_ctx.set(geo.strip().upper() if geo else None)
    try:
        yield
    finally:
        _geo_ctx.reset(token)


def _is_transient_page_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return any(
        x in msg
        for x in (
            "execution context was destroyed",
            "navigation",
            "target closed",
            "frame was detached",
        )
    )


async def _page_title_safe(page: Page, *, attempts: int = 6, delay_ms: int = 1500) -> str:
    """title() падает, если страница ещё редиректится (Cloudflare, meta refresh)."""
    last_exc: Optional[BaseException] = None
    for _ in range(attempts):
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=30_000)
        except Exception:
            pass
        try:
            return (await page.title()) or ""
        except Exception as e:
            last_exc = e
            if not _is_transient_page_error(e):
                raise
            await page.wait_for_timeout(delay_ms)
    if last_exc:
        log.debug("page.title failed after retries: %s", last_exc)
    return ""


def _should_block_request(url: str, resource_type: str) -> bool:
    if not settings.scrape_block_heavy_resources:
        return False
    if resource_type in _BLOCKED_RESOURCE_TYPES:
        return True
    lower = url.lower()
    return any(marker in lower for marker in _AD_URL_MARKERS)


async def _on_route_block_heavy(route: Route) -> None:
    req = route.request
    if _should_block_request(req.url, req.resource_type):
        await route.abort()
    else:
        await route.continue_()


async def attach_resource_blocking(context: BrowserContext) -> None:
    """Блокирует картинки, шрифты, CSS, медиа и типичную рекламу."""
    if not settings.scrape_block_heavy_resources:
        return
    await context.route("**/*", _on_route_block_heavy)


async def wait_cloudflare(page: Page, base_ms: int = 3000) -> None:
    title = await _page_title_safe(page)
    lower = title.lower()
    if "just a moment" in lower or "attention required" in lower:
        log.info("Cloudflare challenge detected, waiting 10s")
        await page.wait_for_timeout(10_000)
        await _page_title_safe(page, attempts=4)
    await page.wait_for_timeout(random.randint(base_ms, base_ms + 2000))


async def verify_proxy_access(page: Page, url: str) -> bool:
    """Проверка: страница открывается, без Cloudflare, есть контент."""
    try:
        response = await page.goto(
            url, wait_until="domcontentloaded", timeout=settings.page_timeout
        )
    except Exception as e:
        log.warning("Proxy verify goto failed %s: %s", url, e)
        return False

    await wait_cloudflare(page)
    title = await _page_title_safe(page)
    lower = title.lower()
    if "just a moment" in lower or "attention required" in lower:
        return False

    content = await page.content()
    if "cf-mitigated" in content:
        return False

    status = response.status if response else 0
    if status >= 400:
        return False
    if len(content) < 500:
        return False
    return True


async def _launch_browser() -> Browser:
    launch_args = {
        "headless": settings.headless,
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ],
    }

    global _playwright, _browser
    if _playwright is None:
        _playwright = await async_playwright().start()
    if _browser is None:
        _browser = await _playwright.chromium.launch(**launch_args)
    return _browser


async def new_context(geo: Optional[str] = None) -> Tuple[BrowserContext, Optional[str]]:
    geo = _resolve_geo(geo)
    proxy = _proxy_pool.get(geo=geo)
    if settings.require_proxy and not proxy:
        raise RuntimeError("No available proxies")

    browser = await _launch_browser()
    ctx_kw: dict = {
        "user_agent": random.choice(USER_AGENTS),
        "viewport": {"width": settings.viewport_width, "height": settings.viewport_height},
        "locale": _browser_locale(geo),
        "timezone_id": _browser_timezone(geo),
        "ignore_https_errors": True,
    }
    pw_proxy = ProxyPool.to_playwright(proxy)
    if pw_proxy:
        ctx_kw["proxy"] = pw_proxy

    context = await browser.new_context(**ctx_kw)
    await attach_resource_blocking(context)
    return context, proxy


async def new_page(geo: Optional[str] = None) -> Tuple[Page, BrowserContext, Optional[str]]:
    context, proxy = await new_context(geo=geo)
    page = await context.new_page()
    if HAS_STEALTH:
        try:
            await stealth_async(page)
        except Exception as e:
            log.debug("stealth: %s", e)
    return page, context, proxy


@asynccontextmanager
async def page_session(
    geo: Optional[str] = None,
    *,
    verify_url: Optional[str] = None,
) -> AsyncIterator[Tuple[Page, Optional[str]]]:
    """
    Контекст страницы с прокси area-{geo}.
    Если задан verify_url — перед yield проверяем доступность; при неудаче пробуем fallback geo.
    """
    geo = _resolve_geo(geo)
    candidates = _proxy_geo_candidates(geo)
    last_geo: Optional[str] = None

    for attempt_geo in candidates:
        context: Optional[BrowserContext] = None
        proxy: Optional[str] = None
        try:
            context, proxy = await new_context(geo=attempt_geo)
            page = await context.new_page()
            if HAS_STEALTH:
                try:
                    await stealth_async(page)
                except Exception as e:
                    log.debug("stealth: %s", e)

            if verify_url:
                log.info(
                    "Checking proxy (area-%s) before scrape: %s",
                    attempt_geo or "?",
                    verify_url,
                )
                if not await verify_proxy_access(page, verify_url):
                    log.warning(
                        "Proxy check failed for geo=%s, trying fallback if any",
                        attempt_geo,
                    )
                    await context.close()
                    last_geo = attempt_geo
                    continue
                log.info("Proxy OK for geo=%s", attempt_geo)

            try:
                yield page, proxy
            finally:
                await context.close()
            return
        except Exception:
            if context is not None:
                await context.close()
            raise

    tried = ", ".join(str(g) for g in candidates)
    raise RuntimeError(
        f"No working proxy for source geo={geo or '?'} (tried: {tried}). "
        f"Last failed geo={last_geo}. Check proxies.txt area-* and connectivity."
    )


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
