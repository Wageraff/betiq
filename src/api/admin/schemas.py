"""Схемы Admin API."""
from __future__ import annotations

from datetime import date, datetime
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


class TeamBriefInGroup(BaseModel):
    id: int
    normalized_key: str
    display_name: str
    sport: Optional[str] = None
    logo_url: Optional[str] = None


class TeamDuplicateGroup(BaseModel):
    canonical_key: str
    canonical_display: str
    teams: list[TeamBriefInGroup]


class TeamDuplicatesOut(BaseModel):
    groups: list[TeamDuplicateGroup]
    total_groups: int


class TeamMergeRequest(BaseModel):
    keeper_id: int
    duplicate_ids: list[int] = Field(min_length=1)


class TeamMergeResponse(BaseModel):
    ok: bool
    message: str
    team: Optional[TeamOut] = None
    merged_count: int


class AdminMatchBrief(BaseModel):
    id: int
    match_key: Optional[str] = None
    slug: Optional[str] = None
    team_home: str
    team_away: str
    team_home_id: Optional[int] = None
    team_away_id: Optional[int] = None
    sport: Optional[str] = None
    competition: Optional[str] = None
    round: Optional[str] = None
    venue_name: Optional[str] = None
    venue_city: Optional[str] = None
    match_date: Optional[datetime] = None
    status: Optional[str] = None
    score: Optional[str] = None
    predictions_count: int = 0
    has_ai: bool = False
    ai_confidence: Optional[str] = None
    has_api_football: bool = False
    has_odds_api: bool = False
    odds_count: int = 0
    has_match_stats: bool = False


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
    full_text: Optional[str] = None
    scraped_at: Optional[datetime] = None
    bets: list[AdminBetOut] = Field(default_factory=list)


class AdminExternalIdOut(BaseModel):
    provider: str
    external_id: str
    link_method: Optional[str] = None
    confidence: Optional[float] = None
    linked_at: Optional[datetime] = None


class AdminMatchStatsOut(BaseModel):
    side: str
    half: str = "full"
    shots_on_goal: Optional[int] = None
    shots_total: Optional[int] = None
    corners: Optional[int] = None
    fouls: Optional[int] = None
    yellow_cards: Optional[int] = None
    red_cards: Optional[int] = None
    possession: Optional[int] = None
    fetched_at: Optional[datetime] = None


class AdminOddsMarketSummaryOut(BaseModel):
    market: str
    count: int
    provider: str


class AdminMatchOddsList(BaseModel):
    match_id: int
    market: Optional[str] = None
    total: int = 0
    market_count: int = 0
    items: list["AdminMatchOddsOut"] = Field(default_factory=list)


class AdminMatchOddsOut(BaseModel):
    provider: str = "the_odds_api"
    bookmaker: str
    market: str
    outcome: str
    odds: Decimal
    point: Optional[Decimal] = None
    is_live: bool = False
    recorded_at: Optional[datetime] = None


class AdminOddsHistoryOut(BaseModel):
    bookmaker: str
    market: str
    outcome: str
    odds_prev: Optional[Decimal] = None
    odds_curr: Decimal
    movement_pct: Optional[Decimal] = None
    direction: Optional[str] = None
    is_significant: bool = False
    recorded_at: Optional[datetime] = None


class AdminLineupOut(BaseModel):
    side: Optional[str] = None
    formation: Optional[str] = None
    coach_name: Optional[str] = None
    players_count: int = 0
    fetched_at: Optional[datetime] = None


class AdminTeamFormOut(BaseModel):
    match_date: Optional[date] = None
    opponent_name: Optional[str] = None
    is_home: Optional[bool] = None
    result: Optional[str] = None
    goals_scored: Optional[int] = None
    goals_conceded: Optional[int] = None
    competition_name: Optional[str] = None


class AdminMatchApiData(BaseModel):
    status: Optional[str] = None
    venue_name: Optional[str] = None
    venue_city: Optional[str] = None
    season: Optional[str] = None
    round: Optional[str] = None
    score: Optional[str] = None
    score_ht: Optional[str] = None
    stats_fetched_at: Optional[datetime] = None
    odds_fetched_at: Optional[datetime] = None
    external_ids: list[AdminExternalIdOut] = Field(default_factory=list)
    match_stats: list[AdminMatchStatsOut] = Field(default_factory=list)
    odds_total: int = 0
    odds_markets: list[AdminOddsMarketSummaryOut] = Field(default_factory=list)
    odds_market: Optional[str] = None
    odds: list[AdminMatchOddsOut] = Field(default_factory=list)
    odds_history: list[AdminOddsHistoryOut] = Field(default_factory=list)
    lineups: list[AdminLineupOut] = Field(default_factory=list)
    team_form_home: list[AdminTeamFormOut] = Field(default_factory=list)
    team_form_away: list[AdminTeamFormOut] = Field(default_factory=list)


class AdminMatchApiPredictionOut(BaseModel):
    winner_team: Optional[str] = None
    winner_comment: Optional[str] = None
    percent_home: Optional[int] = None
    percent_draw: Optional[int] = None
    percent_away: Optional[int] = None
    goals_home: Optional[str] = None
    goals_away: Optional[str] = None
    advice: Optional[str] = None
    form_home: Optional[str] = None
    form_away: Optional[str] = None
    fetched_at: Optional[datetime] = None


class AdminMatchDetail(BaseModel):
    match: AdminMatchBrief
    predictions: list[AdminPredictionOut] = Field(default_factory=list)
    ai_summary: Optional[str] = None
    ai_top_pick: Optional[str] = None
    ai_confidence: Optional[str] = None
    ai_generated_at: Optional[datetime] = None
    ai_model: Optional[str] = None
    api_prediction: Optional[AdminMatchApiPredictionOut] = None
    api_prediction_fetched_at: Optional[datetime] = None
    api_data: Optional[AdminMatchApiData] = None


class AdminAiMatchBrief(BaseModel):
    id: int
    match_title: str
    sport: Optional[str] = None
    match_date: Optional[datetime] = None
    predictions_count: int
    has_ai: bool
    ai_summary: Optional[str] = None
    ai_top_pick: Optional[str] = None
    ai_confidence: Optional[str] = None
    ai_generated_at: Optional[datetime] = None


class AdminAiUpdate(BaseModel):
    ai_summary: Optional[str] = None
    ai_top_pick: Optional[str] = None


class SourceStatsOut(BaseModel):
    """Агрегаты scrape_logs за source_stats_days из config.ini."""

    runs: int = 0
    items_saved: int = 0
    errors: int = 0
    empty_runs: int = 0
    error_rate: float = 0.0
    save_rate: float = 0.0
    health: str = "idle"
    last_run_at: Optional[datetime] = None
    last_error_at: Optional[datetime] = None
    stats_days: int = 7


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    scraper_module: Optional[str] = None
    geo: Optional[str] = None
    is_active: bool
    last_success_at: Optional[datetime] = None
    tier: Optional[str] = None
    stats: Optional[SourceStatsOut] = None


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


class AppLogInfoOut(BaseModel):
    path: str
    exists: bool
    size_bytes: int = 0
    size_human: str = "0 B"
    modified_at: Optional[datetime] = None


class AppLogClearOut(BaseModel):
    ok: bool
    path: str
    bytes_cleared: int = 0


class ApiSyncActionRequest(BaseModel):
    action: str


class ApiProviderQuotaOut(BaseModel):
    configured: bool
    requests_today: Optional[int] = None
    limit_day: Optional[int] = None
    subscription: Optional[str] = None
    remaining: Optional[int] = None
    used: Optional[int] = None
    error: Optional[str] = None


class ApiSyncCoverageMatchOut(BaseModel):
    id: int
    sport: Optional[str] = None
    team_home: str
    team_away: str
    competition: Optional[str] = None
    match_date: Optional[datetime] = None
    status: Optional[str] = None
    has_api_football: bool = False
    has_the_odds_api: bool = False
    odds_count: int = 0
    odds_fetched_at: Optional[datetime] = None
    sport_keys: list[str] = Field(default_factory=list)


class ApiSyncSportKeyOut(BaseModel):
    sport_key: str
    label: str
    sport: Optional[str] = None
    match_count: int
    matches: list[ApiSyncCoverageMatchOut] = Field(default_factory=list)


class ApiSyncCoverageOut(BaseModel):
    odds_sync_mode: str
    upcoming_total: int = 0
    upcoming_by_sport: dict[str, int] = Field(default_factory=dict)
    window: dict[str, object] = Field(default_factory=dict)
    the_odds_api: dict[str, object] = Field(default_factory=dict)
    api_football_odds: dict[str, object] = Field(default_factory=dict)
    odds_in_db: dict[str, int] = Field(default_factory=dict)


class ApiSyncStatusOut(BaseModel):
    api_sync_enabled: bool
    api_football: ApiProviderQuotaOut
    the_odds_api: ApiProviderQuotaOut
    db_counts: dict[str, int]
    coverage: Optional[ApiSyncCoverageOut] = None


class CompetitionTrackingOut(BaseModel):
    id: int
    name: str
    sport: str
    country: Optional[str] = None
    country_code: Optional[str] = None
    matches_upcoming: int = 0
    is_tracked: bool = False
    sync_odds: bool = False
    sync_stats: bool = False
    sync_lineups: bool = False
    odds_markets: Optional[list[str]] = None
    odds_days_ahead: Optional[int] = None


class CompetitionTrackingUpdate(BaseModel):
    is_tracked: Optional[bool] = None
    sync_odds: Optional[bool] = None
    sync_stats: Optional[bool] = None
    sync_lineups: Optional[bool] = None
    odds_markets: Optional[list[str]] = None
    odds_days_ahead: Optional[int] = None
    clear_odds_days_ahead: bool = False


class ApiQuotaStatusOut(BaseModel):
    the_odds_api_remaining: Optional[int] = None
    the_odds_api_used: Optional[int] = None
    api_football_remaining: Optional[int] = None
    api_football_limit: Optional[int] = None
    checked_at: datetime


class CompetitionsListOut(BaseModel):
    items: list[CompetitionTrackingOut]
    total: int
    page: int
    limit: int
    quota: ApiQuotaStatusOut


class CompetitionSyncNowOut(BaseModel):
    competition_id: int
    matches: int
    sport_keys: list[str] = Field(default_factory=list)
    the_odds_api_lines: int = 0
    api_football_lines: int = 0
    error: Optional[str] = None
