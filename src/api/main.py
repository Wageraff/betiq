"""FastAPI application."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

from src.api.admin.router import admin_router
from src.api.routes import matches
from src.config import BASE_DIR, settings

app = FastAPI(
    title="Sports Predictions Aggregator",
    version="1.0.0",
    description="Public API + Admin",
)

app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(matches.router)
app.include_router(admin_router)

uploads = BASE_DIR / "uploads"
uploads.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(uploads)), name="uploads")

_admin_dist = BASE_DIR / "admin-ui" / "dist"
_ASSET_MEDIA = {
    ".js": "application/javascript",
    ".css": "text/css",
    ".map": "application/json",
}


def _admin_index() -> Path:
    index = _admin_dist / "index.html"
    if not index.is_file():
        raise HTTPException(
            503,
            "Admin UI not built. Run: cd admin-ui && npm install && npm run build",
        )
    return index


def _serve_pre_gzip(path: Path, media_type: str, request: Request) -> Response:
    accept = request.headers.get("accept-encoding", "")
    gz_path = Path(f"{path}.gz")
    if "gzip" in accept.lower() and gz_path.is_file():
        body = gz_path.read_bytes()
        return Response(
            content=body,
            media_type=media_type,
            headers={
                "Content-Encoding": "gzip",
                "Content-Length": str(len(body)),
                "Vary": "Accept-Encoding",
                "Cache-Control": "public, max-age=3600",
            },
        )
    body = path.read_bytes()
    return Response(
        content=body,
        media_type=media_type,
        headers={
            "Content-Length": str(len(body)),
            "Cache-Control": "public, max-age=3600",
        },
    )


def _serve_admin_index(request: Request) -> Response:
    """Pre-gzip + Content-Length: chunked-ответ GZipMiddleware обрывается по прямому IP."""
    return _serve_pre_gzip(_admin_index(), "text/html; charset=utf-8", request)


if _admin_dist.is_dir():
    _admin_chunks = _admin_dist / "c"

    @app.get("/admin/c/{chunk_id}.js")
    async def admin_chunk(chunk_id: str, request: Request):
        if not chunk_id.isdigit():
            raise HTTPException(404)
        path = (_admin_chunks / f"{chunk_id}.js").resolve()
        if not str(path).startswith(str(_admin_chunks.resolve())) or not path.is_file():
            raise HTTPException(404)
        return _serve_pre_gzip(path, "application/javascript; charset=utf-8", request)

    _admin_assets = _admin_dist / "assets"
    if _admin_assets.is_dir():

        @app.get("/admin/assets/{asset_path:path}")
        async def admin_asset(asset_path: str, request: Request):
            """Статика админки: pre-gzip .gz при наличии, иначе оригинал."""
            path = (_admin_assets / asset_path).resolve()
            if not str(path).startswith(str(_admin_assets.resolve())):
                raise HTTPException(404)
            if not path.is_file():
                raise HTTPException(404)
            media = _ASSET_MEDIA.get(path.suffix, "application/octet-stream")
            accept = request.headers.get("accept-encoding", "")
            gz_path = Path(f"{path}.gz")
            if "gzip" in accept.lower() and gz_path.is_file():
                return FileResponse(
                    gz_path,
                    media_type=media,
                    headers={
                        "Content-Encoding": "gzip",
                        "Vary": "Accept-Encoding",
                    },
                )
            return FileResponse(path, media_type=media)

    @app.get("/admin")
    async def admin_root(request: Request):
        return _serve_admin_index(request)

    @app.get("/admin/{full_path:path}")
    async def admin_spa(request: Request, full_path: str = ""):
        return _serve_admin_index(request)


@app.get("/health")
async def health():
    return {"status": "ok"}


def main() -> None:
    import uvicorn

    from src.config import setup_logging

    setup_logging()
    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
