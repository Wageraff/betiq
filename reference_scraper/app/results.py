"""Просмотр результатов: ./venv/bin/python -m app.results"""
import argparse
from .database import init_db, get_conn, get_stats
from .settings import DB_PATH, setup_logging


def main():
    setup_logging()
    init_db()
    stats = get_stats()
    print(f"\n=== BetIQ — {DB_PATH} ===")
    print(f"  Страниц:        {stats['pages_total']}")
    print(f"  С контентом:    {stats['pages_with_content']}")
    print(f"  Очередь:        {stats['queue']}")
    if stats.get("by_source"):
        print("  По источникам:")
        for src, cnt in stats["by_source"].items():
            print(f"    {src}: {cnt}")

    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=15)
    args = parser.parse_args()

    with get_conn() as conn:
        rows = conn.execute(
            """SELECT source, h1, title, length(content_html) as clen, url
               FROM pages ORDER BY updated_at DESC LIMIT ?""",
            (args.limit,),
        ).fetchall()

    print(f"\n=== Последние {len(rows)} ===")
    for r in rows:
        name = (r["h1"] or r["title"] or "?")[:55]
        print(f"  [{r['source']}] {name} ({r['clen']} симв.)")


if __name__ == "__main__":
    main()
