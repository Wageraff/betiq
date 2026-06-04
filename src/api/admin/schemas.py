"""Схемы Admin API."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class TeamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    normalized_key: str
    display_name: str
    sport: Optional[str] = None
    logo_url: Optional[str] = None
    aliases: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class TeamUpdate(BaseModel):
    display_name: Optional[str] = None
    sport: Optional[str] = None
    aliases: Optional[str] = None


class AdminMatchBrief(BaseModel):
    id: int
    slug: Optional[str] = None
    team_home: str
    team_away: str
    team_home_id: Optional[int] = None
    team_away_id: Optional[int] = None
    sport: Optional[str] = None
    competition: Optional[str] = None
    match_date: Optional[datetime] = None
    predictions_count: int = 0
    has_ai: bool = False
    ai_confidence: Optional[str] = None


class AdminMatchesList(BaseModel):
    items: list[AdminMatchBrief]
    page: int
    limit: int
    total: int


class AdminBetOut(BaseModel):
    bet_pick: Optional[str] = None
    odds: Optional[Decimal] = None
    bet_type: Optional[str] = None
    is_main: bool = False


class AdminPredictionOut(BaseModel):
    id: int
    source: str
    language: str
    author: Optional[str] = None
    source_url: str
    title: Optional[str] = None
    scraped_at: Optional[datetime] = None
    bets: list[AdminBetOut] = Field(default_factory=list)


class AdminMatchDetail(BaseModel):
    match: AdminMatchBrief
    predictions: list[AdminPredictionOut] = Field(default_factory=list)
    ai_summary: Optional[str] = None
    ai_top_pick: Optional[str] = None
    ai_confidence: Optional[str] = None
    ai_generated_at: Optional[datetime] = None
    ai_model: Optional[str] = None


class AdminAiMatchBrief(BaseModel):
    id: int
    match_title: str
    sport: Optional[str] = None
    match_date: Optional[datetime] = None
    predictions_count: int
    has_ai: bool
    ai_confidence: Optional[str] = None
    ai_generated_at: Optional[datetime] = None


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    scraper_module: Optional[str] = None
    geo: Optional[str] = None
    is_active: bool
    last_success_at: Optional[datetime] = None


class SourceUpdate(BaseModel):
    is_active: Optional[bool] = None
    notes: Optional[str] = None


class ConfigSectionOut(BaseModel):
    name: str
    values: dict[str, str]


class SettingsOut(BaseModel):
    config_sections: list[ConfigSectionOut]
    prompt_template_path: str
    prompt_template_preview: str
    sources: list[SourceOut]
    admin_configured: bool
    anthropic_configured: bool


class ActionRequest(BaseModel):
    source: Optional[str] = None
    limit: Optional[int] = 10
    match_id: Optional[int] = None
    force: bool = False


class ActionResponse(BaseModel):
    ok: bool
    message: str
    job_id: Optional[str] = None


class ActionLogOut(BaseModel):
    lines: list[str]
