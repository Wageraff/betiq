"""
Диагностика Cloudflare / доступности источника.
Запуск: python -m src.scraper.diagnose --source beturi
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import random
from typing import Optional

from sqlalchemy import select

from src.config import settings, setup_logging
from src.db.models import Source
from src.db.session import async_session_factory
from src.scraper.utils.browser import (
    browser_lifecycle,
    ensure_proxy_configured,
    page_session,
    wait_cloudflare,
)
from src.scraper.proxy_pool import ProxyPool

log = logging.getLogger("diagnose")


async def _open_page_without_proxy():
    from playwright.async_api import async_playwright

    from src.config import USER_AGENTS

    try:
        from playwright_stealth import stealth_async

        has_stealth = True
    except Exception:
        has_stealth = False
        stealth_async = None

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=settings.headless,
        args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
    )
    context = await browser.new_context(
        user_agent=random.choice(USER_AGENTS),
        viewport={"width": settings.viewport_width, "height": settings.viewport_height},
        locale="en-US",
        ignore_https_errors=True,
    )
    page = await context.new_page()
    if has_stealth and stealth_async:
        try:
            await stealth_async(page)
        except Exception:
            pass
    return pw, browser, context, page


async def diagnose_url(
    url: str,
    *,
    use_proxy: bool,
    label: str,
    geo: Optional[str] = None,
) -> dict:
    result = {
        "label": label,
        "url": url,
        "ok": False,
        "status": None,
        "title": "",
        "h1": "",
        "has_content": False,
        "cloudflare": False,
    }

    if use_proxy and settings.require_proxy and not ProxyPool().has_proxies:
        result["error"] = "No proxies configured"
        return result

    pw = browser = None
    try:
        if use_proxy:
            async with page_session(geo=geo, verify_url=url) as (page, _):
                result["proxy_geo"] = geo
                return await _check_page(page, url, result, label)
        pw, browser, context, page = await _open_page_without_proxy()
        try:
            return await _check_page(page, url, result, label)
        finally:
            await context.close()
            await browser.close()
            await pw.stop()
    except Exception as e:
        result["error"] = str(e)
        log.exception("Diagnose failed: %s", url)
        if browser:
            await browser.close()
        if pw:
            await pw.stop()
    return result


async def _check_page(page, url: str, result: dict, label: str) -> dict:
    log.info("=== %s: %s ===", label, url)
    response = await page.goto(
        url, wait_until="domcontentloaded", timeout=settings.page_timeout
    )
    await wait_cloudflare(page)
    result["status"] = response.status if response else None
    title = (await page.title()) or ""
    result["title"] = title[:120]
    h1 = await page.evaluate(
        "() => document.querySelector('h1')?.innerText?.trim() || ''"
    )
    result["h1"] = h1[:120]
    content = await page.content()
    result["cloudflare"] = (
        "just a moment" in title.lower()
        or "attention required" in title.lower()
        or "cf-mitigated" in content
    )
    result["has_content"] = bool(h1) and len(content) > 500
    result["ok"] = result["has_content"] and not result["cloudflare"]
    log.info(
        "HTTP=%s title=%r h1=%r ok=%s",
        result["status"],
        result["title"][:50],
        result["h1"][:50],
        result["ok"],
    )
    return result


async def diagnose_source(source: Source) -> list[dict]:
    url = source.base_url.rstrip("/") + source.category_url
    source_geo = (source.geo or settings.proxy_fallback_geo or "GB").upper()
    results = []
    results.append(await diagnose_url(url, use_proxy=False, label="WITHOUT PROXY"))
    if ProxyPool().has_proxies:
        if settings.require_proxy:
            ensure_proxy_configured()
        results.append(
            await diagnose_url(
                url,
                use_proxy=True,
                label=f"WITH PROXY (area-{source_geo})",
                geo=source_geo,
            )
        )
    return results


async def run_diagnose(source_module: str) -> None:
    async with browser_lifecycle():
        async with async_session_factory() as session:
            source = await session.scalar(
                select(Source).where(Source.scraper_module == source_module)
            )
            if not source:
                log.error("Source not found: %s", source_module)
                return
            results = await diagnose_source(source)
            for r in results:
                status = "✅ OK" if r.get("ok") else "❌ FAIL"
                print(f"\n{r.get('label')}: {status}")
                print(f"  HTTP: {r.get('status')}")
                print(f"  Title: {r.get('title')}")
                print(f"  H1: {r.get('h1')}")
                if r.get("error"):
                    print(f"  Error: {r.get('error')}")


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(description="Diagnose source accessibility")
    parser.add_argument("--source", type=str, required=True, help="scraper_module name")
    args = parser.parse_args()
    asyncio.run(run_diagnose(args.source))


if __name__ == "__main__":
    main()
