"""SQLAlchemy 2.0 models — схема из ТЗ раздел 3."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, List, Optional

from sqlalchemy import (
    Boolean,
    CHAR,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    category_url: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=False)
    geo: Mapped[Optional[str]] = mapped_column(String(10))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    scraper_module: Mapped[Optional[str]] = mapped_column(String(100))
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    predictions: Mapped[List["Prediction"]] = relationship(back_populates="source")
    scrape_logs: Mapped[List["ScrapeLog"]] = relationship(back_populates="source")
    health_checks: Mapped[List["HealthCheck"]] = relationship(back_populates="source")
    alert_states: Mapped[List["SourceAlertState"]] = relationship(
        back_populates="source"
    )


class SourceAlertState(Base):
    """Дедуп и snooze Telegram-алертов по источнику."""

    __tablename__ = "source_alert_states"

    source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True
    )
    alert_type: Mapped[str] = mapped_column(String(30), primary_key=True)
    last_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    snoozed_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    source: Mapped["Source"] = relationship(back_populates="alert_states")


class Team(Base):
    __tablename__ = "teams"
    __table_args__ = (Index("idx_teams_sport", "sport"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    normalized_key: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(150), nullable=False)
    sport: Mapped[Optional[str]] = mapped_column(String(50))
    logo_path: Mapped[Optional[str]] = mapped_column(String(500))
    logo_url: Mapped[Optional[str]] = mapped_column(String(500))
    logo_fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    aliases: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    external_ids: Mapped[List["TeamExternalId"]] = relationship(back_populates="team")


class Competition(Base):
    __tablename__ = "competitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    sport: Mapped[str] = mapped_column(String(50), nullable=False)
    country: Mapped[Optional[str]] = mapped_column(String(100))
    country_code: Mapped[Optional[str]] = mapped_column(String(16))
    logo_url: Mapped[Optional[str]] = mapped_column(String(500))
    flag_url: Mapped[Optional[str]] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    is_tracked: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    sync_odds: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    sync_stats: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    sync_lineups: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    odds_markets: Mapped[Optional[str]] = mapped_column(Text)
    odds_days_ahead: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    external_ids: Mapped[List["CompetitionExternalId"]] = relationship(
        back_populates="competition"
    )

    __table_args__ = (
        Index("idx_competitions_name_sport", func.lower(name), sport, unique=True),
    )


class CompetitionExternalId(Base):
    __tablename__ = "competition_external_ids"

    competition_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("competitions.id", ondelete="CASCADE"), primary_key=True
    )
    provider: Mapped[str] = mapped_column(String(30), primary_key=True)
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    external_name: Mapped[Optional[str]] = mapped_column(String(200))
    season: Mapped[Optional[str]] = mapped_column(String(10))

    competition: Mapped["Competition"] = relationship(back_populates="external_ids")


class TeamExternalId(Base):
    __tablename__ = "team_external_ids"

    team_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True
    )
    provider: Mapped[str] = mapped_column(String(30), primary_key=True)
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    external_name: Mapped[Optional[str]] = mapped_column(String(200))
    verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    team: Mapped["Team"] = relationship(back_populates="external_ids")


class MatchExternalId(Base):
    __tablename__ = "match_external_ids"
    __table_args__ = (Index("idx_match_ext_provider_id", "provider", "external_id"),)

    match_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("matches.id", ondelete="CASCADE"), primary_key=True
    )
    provider: Mapped[str] = mapped_column(String(30), primary_key=True)
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    link_method: Mapped[str] = mapped_column(String(20), default="auto", server_default="auto")
    confidence: Mapped[Optional[float]] = mapped_column(Float)

    match: Mapped["Match"] = relationship(back_populates="external_ids")


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (
        Index("idx_matches_match_key", "match_key"),
        Index("idx_matches_match_date", "match_date"),
        Index("idx_matches_sport", "sport"),
        Index("idx_matches_team_home_id", "team_home_id"),
        Index("idx_matches_team_away_id", "team_away_id"),
        Index("idx_matches_status", "status"),
        Index("idx_matches_competition_id", "competition_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_key: Mapped[str] = mapped_column(String(300), unique=True, nullable=False)
    team_home: Mapped[str] = mapped_column(String(150), nullable=False)
    team_away: Mapped[str] = mapped_column(String(150), nullable=False)
    team_home_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("teams.id", ondelete="SET NULL")
    )
    team_away_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("teams.id", ondelete="SET NULL")
    )
    sport: Mapped[Optional[str]] = mapped_column(String(50))
    competition: Mapped[Optional[str]] = mapped_column(String(150))
    competition_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("competitions.id", ondelete="SET NULL")
    )
    match_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status: Mapped[Optional[str]] = mapped_column(String(20))
    venue_name: Mapped[Optional[str]] = mapped_column(String(200))
    venue_city: Mapped[Optional[str]] = mapped_column(String(100))
    season: Mapped[Optional[str]] = mapped_column(String(10))
    round: Mapped[Optional[str]] = mapped_column(String(50))
    score_home: Mapped[Optional[int]] = mapped_column(SmallInteger)
    score_away: Mapped[Optional[int]] = mapped_column(SmallInteger)
    score_ht_home: Mapped[Optional[int]] = mapped_column(SmallInteger)
    score_ht_away: Mapped[Optional[int]] = mapped_column(SmallInteger)
    stats_fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    odds_fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    injuries_fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    h2h_fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    api_prediction_fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    slug: Mapped[Optional[str]] = mapped_column(String(300), unique=True)
    ai_summary: Mapped[Optional[str]] = mapped_column(Text)
    ai_top_pick: Mapped[Optional[str]] = mapped_column(String(200))
    ai_confidence: Mapped[Optional[str]] = mapped_column(String(20))
    ai_generated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    ai_model: Mapped[Optional[str]] = mapped_column(String(100))
    predictions_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    team_home_ref: Mapped[Optional["Team"]] = relationship(
        foreign_keys=[team_home_id], lazy="joined"
    )
    team_away_ref: Mapped[Optional["Team"]] = relationship(
        foreign_keys=[team_away_id], lazy="joined"
    )
    competition_ref: Mapped[Optional["Competition"]] = relationship(
        foreign_keys=[competition_id]
    )
    predictions: Mapped[List["Prediction"]] = relationship(back_populates="match")
    external_ids: Mapped[List["MatchExternalId"]] = relationship(back_populates="match")
    stats: Mapped[List["MatchStats"]] = relationship(back_populates="match")
    lineups: Mapped[List["MatchLineup"]] = relationship(back_populates="match")
    odds: Mapped[List["MatchOdds"]] = relationship(back_populates="match")
    injuries: Mapped[List["MatchInjury"]] = relationship(back_populates="match")
    h2h: Mapped[List["MatchH2H"]] = relationship(back_populates="match")
    api_prediction: Mapped[Optional["MatchApiPrediction"]] = relationship(
        back_populates="match", uselist=False
    )


class MatchStats(Base):
    __tablename__ = "match_stats"
    __table_args__ = (
        UniqueConstraint("match_id", "side", "half", name="uq_match_stats_side_half"),
        Index("idx_match_stats_match_id", "match_id"),
        Index("idx_match_stats_team_id", "team_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("matches.id", ondelete="CASCADE"), nullable=False
    )
    team_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("teams.id", ondelete="SET NULL")
    )
    side: Mapped[str] = mapped_column(String(5), nullable=False)
    half: Mapped[str] = mapped_column(String(5), default="full", server_default="full")
    shots_on_goal: Mapped[Optional[int]] = mapped_column(SmallInteger)
    shots_off_goal: Mapped[Optional[int]] = mapped_column(SmallInteger)
    shots_total: Mapped[Optional[int]] = mapped_column(SmallInteger)
    shots_blocked: Mapped[Optional[int]] = mapped_column(SmallInteger)
    shots_insidebox: Mapped[Optional[int]] = mapped_column(SmallInteger)
    shots_outsidebox: Mapped[Optional[int]] = mapped_column(SmallInteger)
    corners: Mapped[Optional[int]] = mapped_column(SmallInteger)
    fouls: Mapped[Optional[int]] = mapped_column(SmallInteger)
    yellow_cards: Mapped[Optional[int]] = mapped_column(SmallInteger)
    red_cards: Mapped[Optional[int]] = mapped_column(SmallInteger)
    offsides: Mapped[Optional[int]] = mapped_column(SmallInteger)
    possession: Mapped[Optional[int]] = mapped_column(SmallInteger)
    passes_total: Mapped[Optional[int]] = mapped_column(SmallInteger)
    passes_accurate: Mapped[Optional[int]] = mapped_column(SmallInteger)
    goalkeeper_saves: Mapped[Optional[int]] = mapped_column(SmallInteger)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    match: Mapped["Match"] = relationship(back_populates="stats")


class TeamForm(Base):
    __tablename__ = "team_form"
    __table_args__ = (
        UniqueConstraint("team_id", "fixture_external_id", name="uq_team_form_fixture"),
        Index("idx_team_form_team_date", "team_id", "match_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    fixture_external_id: Mapped[Optional[str]] = mapped_column(String(50))
    match_date: Mapped[date] = mapped_column(Date, nullable=False)
    opponent_name: Mapped[Optional[str]] = mapped_column(String(150))
    opponent_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("teams.id", ondelete="SET NULL")
    )
    is_home: Mapped[Optional[bool]] = mapped_column(Boolean)
    result: Mapped[Optional[str]] = mapped_column(CHAR(1))
    goals_scored: Mapped[Optional[int]] = mapped_column(SmallInteger)
    goals_conceded: Mapped[Optional[int]] = mapped_column(SmallInteger)
    corners_for: Mapped[Optional[int]] = mapped_column(SmallInteger)
    corners_against: Mapped[Optional[int]] = mapped_column(SmallInteger)
    yellow_cards: Mapped[Optional[int]] = mapped_column(SmallInteger)
    competition_name: Mapped[Optional[str]] = mapped_column(String(150))


class MatchLineup(Base):
    __tablename__ = "match_lineups"
    __table_args__ = (UniqueConstraint("match_id", "side", name="uq_match_lineups_side"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("matches.id", ondelete="CASCADE"), nullable=False
    )
    team_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("teams.id", ondelete="SET NULL")
    )
    side: Mapped[Optional[str]] = mapped_column(String(5))
    formation: Mapped[Optional[str]] = mapped_column(String(20))
    coach_name: Mapped[Optional[str]] = mapped_column(String(150))
    coach_photo_url: Mapped[Optional[str]] = mapped_column(String(500))
    lineup_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    match: Mapped["Match"] = relationship(back_populates="lineups")


class MatchOdds(Base):
    __tablename__ = "match_odds"
    __table_args__ = (
        UniqueConstraint(
            "match_id",
            "bookmaker",
            "market",
            "outcome",
            "is_live",
            name="uq_match_odds_key",
        ),
        Index("idx_match_odds_match_id", "match_id"),
        Index("idx_match_odds_sport", "sport"),
        Index("idx_match_odds_bookmaker", "bookmaker"),
        Index("idx_match_odds_market", "market"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("matches.id", ondelete="CASCADE"), nullable=False
    )
    sport: Mapped[str] = mapped_column(String(50), nullable=False)
    bookmaker: Mapped[str] = mapped_column(String(80), nullable=False)
    market: Mapped[str] = mapped_column(String(80), nullable=False)
    outcome: Mapped[str] = mapped_column(String(100), nullable=False)
    odds: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    point: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    is_live: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    match: Mapped["Match"] = relationship(back_populates="odds")


class ApiQuotaSnapshot(Base):
    __tablename__ = "api_quota_snapshots"
    __table_args__ = (Index("idx_quota_provider_time", "provider", "recorded_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    requests_remaining: Mapped[Optional[int]] = mapped_column(Integer)
    requests_used: Mapped[Optional[int]] = mapped_column(Integer)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class OddsSyncLog(Base):
    __tablename__ = "odds_sync_log"

    sport_key: Mapped[str] = mapped_column(String(80), primary_key=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OddsHistory(Base):
    __tablename__ = "odds_history"
    __table_args__ = (
        Index("idx_odds_history_match_id", "match_id"),
        Index("idx_odds_history_significant", "is_significant", "recorded_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("matches.id", ondelete="CASCADE"), nullable=False
    )
    bookmaker: Mapped[str] = mapped_column(String(80), nullable=False)
    market: Mapped[str] = mapped_column(String(80), nullable=False)
    outcome: Mapped[str] = mapped_column(String(100), nullable=False)
    odds_prev: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2))
    odds_curr: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    movement_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    direction: Mapped[Optional[str]] = mapped_column(CHAR(4))
    is_significant: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AiChatCache(Base):
    __tablename__ = "ai_chat_cache"
    __table_args__ = (
        Index("idx_ai_cache_key", "cache_key"),
        Index("idx_ai_cache_expires", "expires_at"),
        Index("idx_ai_cache_match", "match_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cache_key: Mapped[str] = mapped_column(String(300), unique=True, nullable=False)
    match_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("matches.id", ondelete="CASCADE")
    )
    question_type: Mapped[str] = mapped_column(String(50), nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=False)
    response_text: Mapped[str] = mapped_column(Text, nullable=False)
    tokens_input: Mapped[Optional[int]] = mapped_column(Integer)
    tokens_output: Mapped[Optional[int]] = mapped_column(Integer)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    hit_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class Prediction(Base):
    __tablename__ = "predictions"
    __table_args__ = (
        Index("idx_predictions_match_id", "match_id"),
        Index("idx_predictions_language", "language"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("matches.id", ondelete="CASCADE")
    )
    source_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("sources.id"))
    source_url: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    title: Mapped[Optional[str]] = mapped_column(Text)
    author: Mapped[Optional[str]] = mapped_column(String(150))
    language: Mapped[str] = mapped_column(String(10), nullable=False)
    full_text: Mapped[Optional[str]] = mapped_column(Text)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    match: Mapped[Optional["Match"]] = relationship(back_populates="predictions")
    source: Mapped[Optional["Source"]] = relationship(back_populates="predictions")
    bets: Mapped[List["PredictionBet"]] = relationship(
        back_populates="prediction", cascade="all, delete-orphan"
    )


class PredictionBet(Base):
    __tablename__ = "prediction_bets"
    __table_args__ = (Index("idx_prediction_bets_prediction_id", "prediction_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prediction_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("predictions.id", ondelete="CASCADE"), nullable=False
    )
    bet_type: Mapped[Optional[str]] = mapped_column(String(100))
    bet_pick: Mapped[Optional[str]] = mapped_column(String(100))
    odds: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2))
    is_main: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    prediction: Mapped["Prediction"] = relationship(back_populates="bets")


class ScrapeLog(Base):
    __tablename__ = "scrape_logs"
    __table_args__ = (Index("idx_scrape_logs_source_id", "source_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("sources.id"))
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    items_found: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    items_new: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error_msg: Mapped[Optional[str]] = mapped_column(Text)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    source: Mapped[Optional["Source"]] = relationship(back_populates="scrape_logs")


class HealthCheck(Base):
    __tablename__ = "health_checks"
    __table_args__ = (Index("idx_health_checks_source_id", "source_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("sources.id"))
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    is_accessible: Mapped[Optional[bool]] = mapped_column(Boolean)
    status_code: Mapped[Optional[int]] = mapped_column(Integer)
    html_structure_ok: Mapped[Optional[bool]] = mapped_column(Boolean)
    alert_sent: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    details: Mapped[Optional[str]] = mapped_column(Text)

    source: Mapped[Optional["Source"]] = relationship(back_populates="health_checks")


class MatchInjury(Base):
    __tablename__ = "match_injuries"
    __table_args__ = (Index("idx_match_injuries_match_id", "match_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("matches.id", ondelete="CASCADE"), nullable=False
    )
    team_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("teams.id", ondelete="SET NULL")
    )
    team_name: Mapped[Optional[str]] = mapped_column(String(150))
    side: Mapped[Optional[str]] = mapped_column(String(10))
    player_name: Mapped[str] = mapped_column(String(150), nullable=False)
    player_id_ext: Mapped[Optional[str]] = mapped_column(String(20))
    position: Mapped[Optional[str]] = mapped_column(String(50))
    injury_type: Mapped[Optional[str]] = mapped_column(String(100))
    reason: Mapped[Optional[str]] = mapped_column(String(200))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    match: Mapped["Match"] = relationship(back_populates="injuries")


class MatchH2H(Base):
    __tablename__ = "match_h2h"
    __table_args__ = (
        UniqueConstraint("match_id", "fixture_external_id", name="uq_h2h_match_fixture"),
        Index("idx_match_h2h_match_id", "match_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("matches.id", ondelete="CASCADE"), nullable=False
    )
    fixture_external_id: Mapped[str] = mapped_column(String(30), nullable=False)
    match_date: Mapped[Optional[date]] = mapped_column(Date)
    home_team: Mapped[Optional[str]] = mapped_column(String(150))
    away_team: Mapped[Optional[str]] = mapped_column(String(150))
    score_home: Mapped[Optional[int]] = mapped_column(SmallInteger)
    score_away: Mapped[Optional[int]] = mapped_column(SmallInteger)
    competition_name: Mapped[Optional[str]] = mapped_column(String(150))
    status: Mapped[Optional[str]] = mapped_column(String(20))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    match: Mapped["Match"] = relationship(back_populates="h2h")


class MatchApiPrediction(Base):
    __tablename__ = "match_api_predictions"
    __table_args__ = (
        Index("idx_match_api_predictions_match_id", "match_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("matches.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    winner_team: Mapped[Optional[str]] = mapped_column(String(150))
    winner_comment: Mapped[Optional[str]] = mapped_column(String(300))
    percent_home: Mapped[Optional[int]] = mapped_column(SmallInteger)
    percent_draw: Mapped[Optional[int]] = mapped_column(SmallInteger)
    percent_away: Mapped[Optional[int]] = mapped_column(SmallInteger)
    goals_home: Mapped[Optional[str]] = mapped_column(String(20))
    goals_away: Mapped[Optional[str]] = mapped_column(String(20))
    advice: Mapped[Optional[str]] = mapped_column(Text)
    form_home: Mapped[Optional[str]] = mapped_column(String(10))
    form_away: Mapped[Optional[str]] = mapped_column(String(10))
    raw_json: Mapped[Optional[Any]] = mapped_column(JSONB)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    match: Mapped["Match"] = relationship(back_populates="api_prediction")
