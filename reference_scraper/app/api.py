"""REST API для спарсенных страниц BetIQ."""
import logging
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .settings import API_HOST, API_PORT, API_TOKEN, setup_logging
from .database import init_db, get_conn, get_stats

setup_logging()
log = logging.getLogger("api")
init_db()

app = FastAPI(title="BetIQ Parser API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def verify_token(authorization: Optional[str] = Header(None)):
    if not API_TOKEN or API_TOKEN.startswith("CHANGE_ME"):
        return True
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    if authorization.replace("Bearer ", "", 1).strip() != API_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")
    return True


class PageShort(BaseModel):
    id: int
    url: str
    slug: Optional[str]
    source: Optional[str]
    title: Optional[str]
    h1: Optional[str]
    updated_at: str


class PageFull(BaseModel):
    id: int
    url: str
    slug: Optional[str]
    source: Optional[str]
    title: Optional[str]
    meta_description: Optional[str]
    h1: Optional[str]
    content_html: Optional[str]
    content_hash: Optional[str]
    scraped_at: str
    updated_at: str


@app.get("/")
def root():
    return {
        "name": "BetIQ Parser API",
        "endpoints": {
            "GET /stats": "статистика",
            "GET /pages": "список страниц",
            "GET /pages/{slug}": "одна страница",
            "GET /pages/by-url?url=...": "по URL",
        },
    }


@app.get("/stats")
def stats(_=Depends(verify_token)):
    return get_stats()


@app.get("/pages", response_model=list[PageShort])
def list_pages(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    search: Optional[str] = None,
    source: Optional[str] = None,
    _=Depends(verify_token),
):
    where, params = [], []
    if search:
        where.append("(title LIKE ? OR slug LIKE ? OR h1 LIKE ?)")
        params.extend([f"%{search}%"] * 3)
    if source:
        where.append("source LIKE ?")
        params.append(f"%{source}%")
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    sql = f"""
        SELECT id, url, slug, source, title, h1, updated_at
        FROM pages {where_sql}
        ORDER BY updated_at DESC LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


@app.get("/pages/by-url", response_model=PageFull)
def get_by_url(url: str = Query(...), _=Depends(verify_token)):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM pages WHERE url=?", (url,)).fetchone()
    if not row:
        raise HTTPException(404, "Not found")
    return dict(row)


@app.get("/pages/{slug}", response_model=PageFull)
def get_by_slug(slug: str, _=Depends(verify_token)):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM pages WHERE slug=?", (slug,)).fetchone()
    if not row:
        raise HTTPException(404, "Not found")
    return dict(row)


def main():
    import uvicorn
    uvicorn.run("app.api:app", host=API_HOST, port=API_PORT, log_level="info")


if __name__ == "__main__":
    main()
