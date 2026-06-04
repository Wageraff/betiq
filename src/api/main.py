"""FastAPI application."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.api.admin.router import admin_router
from src.api.routes import matches
from src.config import BASE_DIR, settings

app = FastAPI(
    title="Sports Predictions Aggregator",
    version="1.0.0",
    description="Public API + Admin",
)

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
if _admin_dist.is_dir():
    app.mount("/admin/assets", StaticFiles(directory=str(_admin_dist / "assets")), name="admin-assets")

    @app.get("/admin")
    async def admin_root():
        return FileResponse(_admin_dist / "index.html")

    @app.get("/admin/{full_path:path}")
    async def admin_spa(full_path: str = ""):
        index = _admin_dist / "index.html"
        if not index.is_file():
            return {
                "detail": "Admin UI not built. Run: cd admin-ui && npm install && npm run build"
            }
        return FileResponse(index)


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
