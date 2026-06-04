"""Зависимости Admin API."""
from __future__ import annotations

from fastapi import Header, HTTPException

from src.config import settings


async def require_admin(x_admin_key: str = Header(..., alias="X-Admin-Key")) -> None:
    if not settings.admin_api_key:
        raise HTTPException(
            status_code=503,
            detail="ADMIN_API_KEY is not configured on the server",
        )
    if x_admin_key != settings.admin_api_key:
        raise HTTPException(status_code=401, detail="Invalid admin key")
