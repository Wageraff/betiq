"""SQLAlchemy 2.0 models — схема из ТЗ раздел 3."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
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


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (
        Index("idx_matches_match_key", "match_key"),
        Index("idx_matches_match_date", "match_date"),
        Index("idx_matches_sport", "sport"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_key: Mapped[str] = mapped_column(String(300), unique=True, nullable=False)
    team_home: Mapped[str] = mapped_column(String(150), nullable=False)
    team_away: Mapped[str] = mapped_column(String(150), nullable=False)
    sport: Mapped[Optional[str]] = mapped_column(String(50))
    competition: Mapped[Optional[str]] = mapped_column(String(150))
    match_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
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

    predictions: Mapped[List["Prediction"]] = relationship(back_populates="match")


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
