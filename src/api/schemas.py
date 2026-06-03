"""Pydantic-схемы REST API (camelCase в JSON)."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class AiOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    summary: Optional[str] = None
    top_pick: Optional[str] = Field(None, serialization_alias="topPick")
    confidence: Optional[str] = None
    generated_at: Optional[datetime] = Field(None, serialization_alias="generatedAt")


class BetOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    bet_type: Optional[str] = Field(None, serialization_alias="betType")
    bet_pick: Optional[str] = Field(None, serialization_alias="betPick")
    odds: Optional[Decimal] = None
    is_main: bool = Field(False, serialization_alias="isMain")


class PredictionOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    source: str
    language: str
    author: Optional[str] = None
    title: Optional[str] = None
    source_url: str = Field(serialization_alias="sourceUrl")
    published_at: Optional[datetime] = Field(None, serialization_alias="publishedAt")
    bets: List[BetOut] = []


class MatchBriefOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    slug: Optional[str] = None
    team_home: str = Field(serialization_alias="teamHome")
    team_away: str = Field(serialization_alias="teamAway")
    sport: Optional[str] = None
    competition: Optional[str] = None
    match_date: Optional[datetime] = Field(None, serialization_alias="matchDate")
    predictions_count: int = Field(0, serialization_alias="predictionsCount")
    ai: Optional[AiOut] = None


class MatchDetailOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    slug: Optional[str] = None
    team_home: str = Field(serialization_alias="teamHome")
    team_away: str = Field(serialization_alias="teamAway")
    sport: Optional[str] = None
    competition: Optional[str] = None
    match_date: Optional[datetime] = Field(None, serialization_alias="matchDate")
    predictions_count: int = Field(0, serialization_alias="predictionsCount")
    ai: Optional[AiOut] = None


class MatchDetailResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    match: MatchDetailOut
    predictions: List[PredictionOut] = []


class PredictionsOnlyResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    predictions: List[PredictionOut] = []


class MatchesListResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    items: List[MatchBriefOut]
    page: int
    limit: int
    total: int


class SportCountOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    sport: str
    count: int


class SportsListResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    sports: List[SportCountOut] = []
