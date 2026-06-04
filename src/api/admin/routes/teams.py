"""Admin: справочник команд."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.admin.deps import require_admin
from src.api.admin.schemas import TeamOut, TeamUpdate
from src.api.deps import get_db
from src.config import BASE_DIR
from src.db.models import Team

router = APIRouter(prefix="/teams", tags=["admin-teams"])

UPLOAD_ROOT = BASE_DIR / "uploads" / "teams"
ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".webp", ".svg"}


def _logo_url(team: Team) -> Optional[str]:
    if team.logo_path:
        return f"/uploads/teams/{Path(team.logo_path).name}"
    return None


def _team_out(team: Team) -> TeamOut:
    return TeamOut(
        id=team.id,
        normalized_key=team.normalized_key,
        display_name=team.display_name,
        sport=team.sport,
        logo_url=_logo_url(team),
        aliases=team.aliases,
        created_at=team.created_at,
        updated_at=team.updated_at,
    )


@router.get("", response_model=list[TeamOut])
async def list_teams(
    q: Optional[str] = Query(None, description="Поиск по названию или ключу"),
    sport: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin),
):
    stmt = select(Team)
    if sport:
        stmt = stmt.where(Team.sport == sport)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(Team.display_name.ilike(like), Team.normalized_key.ilike(like))
        )
    stmt = stmt.order_by(Team.display_name).offset((page - 1) * limit).limit(limit)
    teams = (await db.scalars(stmt)).all()
    return [_team_out(t) for t in teams]


@router.get("/{team_id}", response_model=TeamOut)
async def get_team(
    team_id: int,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin),
):
    team = await db.get(Team, team_id)
    if not team:
        raise HTTPException(404, "Team not found")
    return _team_out(team)


@router.patch("/{team_id}", response_model=TeamOut)
async def update_team(
    team_id: int,
    body: TeamUpdate,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin),
):
    team = await db.get(Team, team_id)
    if not team:
        raise HTTPException(404, "Team not found")
    if body.display_name is not None:
        team.display_name = body.display_name.strip()
    if body.sport is not None:
        team.sport = body.sport or None
    if body.aliases is not None:
        team.aliases = body.aliases
    await db.commit()
    await db.refresh(team)
    return _team_out(team)


@router.post("/{team_id}/logo", response_model=TeamOut)
async def upload_logo(
    team_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin),
):
    team = await db.get(Team, team_id)
    if not team:
        raise HTTPException(404, "Team not found")

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXT:
        raise HTTPException(400, f"Allowed: {', '.join(ALLOWED_EXT)}")

    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    dest_name = f"team_{team_id}{suffix}"
    dest = UPLOAD_ROOT / dest_name
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(400, "Max file size 5MB")
    dest.write_bytes(content)

    team.logo_path = dest_name
    await db.commit()
    await db.refresh(team)
    return _team_out(team)
