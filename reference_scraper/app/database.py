"""
Работа с SQLite — очередь URL и спарсенные страницы (прогнозы/статьи).
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from urllib.parse import urlparse

from .settings import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS urls_queue (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    url         TEXT UNIQUE NOT NULL,
    status      TEXT DEFAULT 'pending',
    attempts    INTEGER DEFAULT 0,
    last_error  TEXT,
    added_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_queue_status ON urls_queue(status);

CREATE TABLE IF NOT EXISTS pages (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    url                 TEXT UNIQUE NOT NULL,
    slug                TEXT,
    source              TEXT,
    title               TEXT,
    meta_description    TEXT,
    h1                  TEXT,
    content_html        TEXT,
    content_hash        TEXT,
    scraped_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pages_slug ON pages(slug);
CREATE INDEX IF NOT EXISTS idx_pages_source ON pages(source);
CREATE INDEX IF NOT EXISTS idx_pages_updated ON pages(updated_at);
"""


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    try:
        yield conn
    finally:
        conn.close()


def add_urls_to_queue(urls: list[str]) -> int:
    added = 0
    with get_conn() as conn:
        cur = conn.cursor()
        for url in urls:
            cur.execute("INSERT OR IGNORE INTO urls_queue (url) VALUES (?)", (url,))
            added += cur.rowcount
        conn.commit()
    return added


def reset_done_without_content(urls: list[str], min_len: int) -> int:
    if not urls:
        return 0
    with get_conn() as conn:
        placeholders = ",".join("?" * len(urls))
        cur = conn.execute(
            f"""UPDATE urls_queue
                SET status='pending', attempts=0, last_error=NULL,
                    updated_at=CURRENT_TIMESTAMP
                WHERE url IN ({placeholders})
                  AND status='done'
                  AND url IN (
                      SELECT url FROM pages
                      WHERE content_html IS NULL
                         OR length(content_html) < ?
                  )""",
            [*urls, min_len],
        )
        conn.commit()
        return cur.rowcount


def reset_urls_for_retry(urls: list[str]) -> int:
    if not urls:
        return 0
    with get_conn() as conn:
        placeholders = ",".join("?" * len(urls))
        cur = conn.execute(
            f"""UPDATE urls_queue
                SET status='pending', attempts=0, last_error=NULL,
                    updated_at=CURRENT_TIMESTAMP
                WHERE url IN ({placeholders}) AND status='failed'""",
            urls,
        )
        conn.commit()
        return cur.rowcount


def get_failed_urls() -> list[tuple[str, str | None]]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT url, last_error FROM urls_queue
               WHERE status='failed' ORDER BY updated_at DESC"""
        ).fetchall()
    return [(r["url"], r["last_error"]) for r in rows]


def get_pending_urls(limit: int | None = None, max_attempts: int = 3) -> list[str]:
    q = "SELECT url FROM urls_queue WHERE status IN ('pending', 'failed') AND attempts < ?"
    params: list = [max_attempts]
    if limit:
        q += " LIMIT ?"
        params.append(limit)
    with get_conn() as conn:
        rows = conn.execute(q, params).fetchall()
    return [r["url"] for r in rows]


def mark_processing(url: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE urls_queue SET status='processing', updated_at=CURRENT_TIMESTAMP WHERE url=?",
            (url,),
        )
        conn.commit()


def mark_done(url: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE urls_queue SET status='done', updated_at=CURRENT_TIMESTAMP WHERE url=?",
            (url,),
        )
        conn.commit()


def mark_failed(url: str, error: str):
    with get_conn() as conn:
        conn.execute(
            """UPDATE urls_queue SET status='failed', attempts=attempts+1,
               last_error=?, updated_at=CURRENT_TIMESTAMP WHERE url=?""",
            (str(error)[:500], url),
        )
        conn.commit()


def save_page(data: dict):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO pages (url, slug, source, title, meta_description, h1,
                               content_html, content_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                slug=excluded.slug,
                source=excluded.source,
                title=excluded.title,
                meta_description=excluded.meta_description,
                h1=excluded.h1,
                content_html=excluded.content_html,
                content_hash=excluded.content_hash,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                data["url"],
                data.get("slug"),
                data.get("source"),
                data.get("title"),
                data.get("meta_description"),
                data.get("h1"),
                data.get("content_html"),
                data.get("content_hash"),
            ),
        )
        conn.commit()


def get_stats() -> dict:
    with get_conn() as conn:
        queue_stats = {
            row["status"]: row["cnt"]
            for row in conn.execute(
                "SELECT status, COUNT(*) cnt FROM urls_queue GROUP BY status"
            ).fetchall()
        }
        total = conn.execute("SELECT COUNT(*) c FROM pages").fetchone()["c"]
        with_content = conn.execute(
            "SELECT COUNT(*) c FROM pages WHERE content_html IS NOT NULL AND length(content_html) > 200"
        ).fetchone()["c"]
        by_source = conn.execute(
            "SELECT source, COUNT(*) cnt FROM pages GROUP BY source ORDER BY cnt DESC LIMIT 20"
        ).fetchall()
    return {
        "queue": queue_stats,
        "pages_total": total,
        "pages_with_content": with_content,
        "by_source": {r["source"]: r["cnt"] for r in by_source},
    }


def source_from_url(url: str) -> str:
    try:
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return ""
