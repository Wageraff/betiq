"""
BetIQ — парсер страниц с прогнозами (Playwright + прокси).
Основан на bwb-parser, без iframe — главное: контент статьи.

Запуск:
    ./venv/bin/python -m app.scraper
    ./venv/bin/python -m app.scraper --limit 10
    ./venv/bin/python -m app.scraper --input failed_urls.txt
"""
import argparse
import asyncio
import hashlib
import logging
import random
import sys
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import async_playwright

try:
    from playwright_stealth import stealth_async
    HAS_STEALTH = True
except Exception:
    HAS_STEALTH = False

from .settings import (
    URLS_FILE, FAILED_URLS_FILE, REQUIRE_PROXY,
    CONCURRENCY, MIN_DELAY, MAX_DELAY, MAX_ATTEMPTS,
    PAGE_TIMEOUT, HEADLESS, VIEWPORT_WIDTH, VIEWPORT_HEIGHT,
    MIN_CONTENT_LENGTH, SEL_CONTENT_BLOCKS, SEL_TITLE_H1,
    USER_AGENTS, setup_logging,
)
from .database import (
    init_db, add_urls_to_queue, reset_urls_for_retry, reset_done_without_content,
    get_pending_urls, get_failed_urls, mark_processing, mark_done, mark_failed,
    save_page, source_from_url,
)
from .proxy_pool import ProxyPool
from .url_list import load_urls, save_failed_urls

log = logging.getLogger("scraper")
proxy_pool = ProxyPool()
_PROXY_ERRORS = ("ERR_CERT", "ERR_CONNECTION", "ERR_PROXY", "ERR_TUNNEL", "net::")


def ensure_proxy_configured():
    if REQUIRE_PROXY and not proxy_pool.has_proxies:
        log.error("Прокси обязательны! Добавьте их в proxies.txt")
        sys.exit(1)


def load_urls_into_queue(input_file: str) -> int:
    path = Path(input_file)
    if not path.exists():
        log.warning(f"Файл URL не найден: {path}")
        return 0
    urls = load_urls(path)
    if not urls:
        log.warning(f"Файл {path} пуст")
        return 0
    added = add_urls_to_queue(urls)
    retried = reset_urls_for_retry(urls)
    recontent = reset_done_without_content(urls, MIN_CONTENT_LENGTH)
    log.info(
        f"Из {path.name}: {len(urls)} URL | новых: {added} | "
        f"failed→pending: {retried} | без контента (повтор): {recontent}"
    )
    return len(urls)


def _content_js() -> str:
    selectors = SEL_CONTENT_BLOCKS or ["article"]
    return f"""
    () => {{
        const sels = {selectors!r};
        for (const s of sels) {{
            const el = document.querySelector(s);
            if (el && el.innerHTML && el.innerHTML.length > 50) {{
                return el.innerHTML;
            }}
        }}
        const main = document.querySelector('main');
        if (main && main.innerHTML.length > 100) return main.innerHTML;
        return '';
    }}
    """


async def scrape_one(playwright, url: str) -> dict:
    proxy = proxy_pool.get()
    if REQUIRE_PROXY and not proxy:
        raise RuntimeError("Нет доступных прокси")

    user_agent = random.choice(USER_AGENTS)
    launch_args = {
        "headless": HEADLESS,
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ],
        "proxy": ProxyPool.to_playwright(proxy),
    }

    browser = await playwright.chromium.launch(**launch_args)
    context = await browser.new_context(
        user_agent=user_agent,
        viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
        locale="ru-RU",
        timezone_id="Europe/Moscow",
        ignore_https_errors=True,
    )
    page = await context.new_page()

    if HAS_STEALTH:
        try:
            await stealth_async(page)
        except Exception as e:
            log.debug(f"stealth: {e}")

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
        await page.wait_for_timeout(random.randint(2000, 4000))

        content_html = await page.evaluate(_content_js())
        title = (await page.title()) or ""
        meta_description = await page.evaluate(
            "() => document.querySelector('meta[name=\"description\"]')?.content || ''"
        )
        h1 = await page.evaluate(
            f"() => document.querySelector({SEL_TITLE_H1!r})?.innerText?.trim() || ''"
        )

        if len(content_html or "") < MIN_CONTENT_LENGTH:
            raise RuntimeError(
                f"Мало контента ({len(content_html or '')} симв.) — проверь селекторы в config.ini"
            )

        path = urlparse(url).path.rstrip("/")
        slug = path.split("/")[-1] if path else url

        return {
            "url": url,
            "slug": slug,
            "source": source_from_url(url),
            "title": title,
            "meta_description": meta_description,
            "h1": h1,
            "content_html": content_html,
            "content_hash": hashlib.md5(content_html.encode("utf-8")).hexdigest(),
        }
    except Exception as e:
        if proxy and any(x in str(e) for x in _PROXY_ERRORS):
            proxy_pool.report_failure(proxy)
        raise
    finally:
        await context.close()
        await browser.close()


async def worker(playwright, semaphore, url: str):
    async with semaphore:
        mark_processing(url)
        for attempt in range(2):
            try:
                log.info(f"{'↻ ' if attempt else '→ '}{url}")
                data = await scrape_one(playwright, url)
                if not data.get("title") and not data.get("h1"):
                    raise RuntimeError("Пустой title/h1 — возможна блокировка")
                save_page(data)
                mark_done(url)
                log.info(f"✓ [{data['source']}] {data.get('h1') or data.get('title','')[:70]}")
                break
            except Exception as e:
                if attempt == 0 and any(x in str(e) for x in _PROXY_ERRORS):
                    continue
                log.error(f"✗ {url}: {e}")
                mark_failed(url, str(e))
                break
        await asyncio.sleep(random.uniform(MIN_DELAY, MAX_DELAY))


def export_failed_urls():
    failed = get_failed_urls()
    if not failed:
        log.info("Все URL успешны — failed_urls.txt не создан.")
        return
    save_failed_urls(FAILED_URLS_FILE, failed)
    log.info(f"Неудачные ({len(failed)}) → {FAILED_URLS_FILE}")


async def run_async(limit: int | None, input_file: str):
    ensure_proxy_configured()
    init_db()
    load_urls_into_queue(input_file)
    urls = get_pending_urls(limit=limit, max_attempts=MAX_ATTEMPTS)
    if not urls:
        log.info("Нечего парсить.")
        return
    log.info(
        f"К парсингу: {len(urls)} URL | concurrency={CONCURRENCY} | "
        f"delay={MIN_DELAY}-{MAX_DELAY}s"
    )
    sem = asyncio.Semaphore(CONCURRENCY)
    async with async_playwright() as p:
        await asyncio.gather(*[worker(p, sem, u) for u in urls])
    export_failed_urls()
    log.info("Готово.")


def main():
    setup_logging()
    parser = argparse.ArgumentParser(description="BetIQ parser")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--input", type=str, default=URLS_FILE)
    args = parser.parse_args()
    try:
        asyncio.run(run_async(args.limit, args.input))
    except KeyboardInterrupt:
        export_failed_urls()
        sys.exit(0)


if __name__ == "__main__":
    main()
