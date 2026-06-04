"""Admin: настройки и источники."""
from __future__ import annotations

import configparser

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.admin.deps import require_admin
from src.api.admin.schemas import ConfigSectionOut, SettingsOut, SourceOut, SourceUpdate
from src.api.deps import get_db
from src.config import BASE_DIR, CONFIG_PATH, settings
from src.db.models import Source

router = APIRouter(prefix="/settings", tags=["admin-settings"])


def _read_config_sections() -> list[ConfigSectionOut]:
    cp = configparser.ConfigParser(interpolation=None)
    if CONFIG_PATH.exists():
        cp.read(CONFIG_PATH, encoding="utf-8")
    return [
        ConfigSectionOut(name=sec, values=dict(cp.items(sec)))
        for sec in cp.sections()
    ]


@router.get("", response_model=SettingsOut)
async def get_settings(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin),
):
    from src.ai.prompt_template import load_prompt_template, resolve_prompt_path

    path = resolve_prompt_path()
    try:
        preview = load_prompt_template()[:2000]
    except FileNotFoundError:
        preview = ""

    sources = (await db.scalars(select(Source).order_by(Source.id))).all()
    return SettingsOut(
        config_sections=_read_config_sections(),
        prompt_template_path=str(path),
        prompt_template_preview=preview,
        sources=[
            SourceOut(
                id=s.id,
                name=s.name,
                scraper_module=s.scraper_module,
                geo=s.geo,
                is_active=s.is_active,
                last_success_at=s.last_success_at,
            )
            for s in sources
        ],
        admin_configured=bool(settings.admin_api_key),
        anthropic_configured=bool(settings.anthropic_api_key),
    )


@router.patch("/sources/{source_id}", response_model=SourceOut)
async def update_source(
    source_id: int,
    body: SourceUpdate,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin),
):
    source = await db.get(Source, source_id)
    if not source:
        raise HTTPException(404, "Source not found")
    if body.is_active is not None:
        source.is_active = body.is_active
    if body.notes is not None:
        source.notes = body.notes
    await db.commit()
    await db.refresh(source)
    return SourceOut(
        id=source.id,
        name=source.name,
        scraper_module=source.scraper_module,
        geo=source.geo,
        is_active=source.is_active,
        last_success_at=source.last_success_at,
    )
