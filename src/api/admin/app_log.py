"""Доступ к app.log из config.ini (только внутри проекта)."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException

from src.config import BASE_DIR, settings


def resolve_app_log_path() -> Path:
    path = Path(settings.log_file)
    if not path.is_absolute():
        path = BASE_DIR / path
    resolved = path.resolve()
    base = BASE_DIR.resolve()
    try:
        resolved.relative_to(base)
    except ValueError as e:
        raise HTTPException(403, "Log path outside project directory") from e
    return resolved


def human_size(num_bytes: int) -> str:
    if num_bytes < 1024:
        return f"{num_bytes} B"
    units = ("KB", "MB", "GB", "TB")
    size = float(num_bytes)
    for unit in units:
        size /= 1024
        if size < 1024:
            return f"{size:.1f} {unit}"
    return f"{size:.1f} PB"


def app_log_info() -> dict:
    path = resolve_app_log_path()
    if not path.exists():
        return {
            "path": str(path),
            "exists": False,
            "size_bytes": 0,
            "size_human": "0 B",
            "modified_at": None,
        }
    stat = path.stat()
    modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
    return {
        "path": str(path),
        "exists": True,
        "size_bytes": stat.st_size,
        "size_human": human_size(stat.st_size),
        "modified_at": modified,
    }


def clear_app_log() -> int:
    path = resolve_app_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    prev_size = path.stat().st_size if path.exists() else 0
    with open(path, "w", encoding="utf-8"):
        pass
    return prev_size
