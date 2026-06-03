"""Initial schema: sources, matches, predictions, bets, logs.

Revision ID: 001
Revises:
Create Date: 2026-06-02

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("category_url", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=10), nullable=False),
        sa.Column("geo", sa.String(length=10), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=True),
        sa.Column("scraper_module", sa.String(length=100), nullable=True),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "matches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("match_key", sa.String(length=300), nullable=False),
        sa.Column("team_home", sa.String(length=150), nullable=False),
        sa.Column("team_away", sa.String(length=150), nullable=False),
        sa.Column("sport", sa.String(length=50), nullable=True),
        sa.Column("competition", sa.String(length=150), nullable=True),
        sa.Column("match_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("slug", sa.String(length=300), nullable=True),
        sa.Column("ai_summary", sa.Text(), nullable=True),
        sa.Column("ai_top_pick", sa.String(length=200), nullable=True),
        sa.Column("ai_confidence", sa.String(length=20), nullable=True),
        sa.Column("ai_generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ai_model", sa.String(length=100), nullable=True),
        sa.Column("predictions_count", sa.Integer(), server_default="0", nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("match_key"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("idx_matches_match_key", "matches", ["match_key"], unique=False)
    op.create_index("idx_matches_match_date", "matches", ["match_date"], unique=False)
    op.create_index("idx_matches_sport", "matches", ["sport"], unique=False)

    op.create_table(
        "predictions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=True),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("author", sa.String(length=150), nullable=True),
        sa.Column("language", sa.String(length=10), nullable=False),
        sa.Column("full_text", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scraped_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_url"),
    )
    op.create_index("idx_predictions_match_id", "predictions", ["match_id"], unique=False)
    op.create_index("idx_predictions_language", "predictions", ["language"], unique=False)

    op.create_table(
        "prediction_bets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("prediction_id", sa.Integer(), nullable=False),
        sa.Column("bet_type", sa.String(length=100), nullable=True),
        sa.Column("bet_pick", sa.String(length=100), nullable=True),
        sa.Column("odds", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("is_main", sa.Boolean(), server_default="false", nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=True),
        sa.ForeignKeyConstraint(["prediction_id"], ["predictions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_prediction_bets_prediction_id",
        "prediction_bets",
        ["prediction_id"],
        unique=False,
    )

    op.create_table(
        "scrape_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("items_found", sa.Integer(), server_default="0", nullable=True),
        sa.Column("items_new", sa.Integer(), server_default="0", nullable=True),
        sa.Column("error_msg", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_scrape_logs_source_id", "scrape_logs", ["source_id"], unique=False)

    op.create_table(
        "health_checks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("is_accessible", sa.Boolean(), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("html_structure_ok", sa.Boolean(), nullable=True),
        sa.Column("alert_sent", sa.Boolean(), server_default="false", nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_health_checks_source_id", "health_checks", ["source_id"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_health_checks_source_id", table_name="health_checks")
    op.drop_table("health_checks")
    op.drop_index("idx_scrape_logs_source_id", table_name="scrape_logs")
    op.drop_table("scrape_logs")
    op.drop_index("idx_prediction_bets_prediction_id", table_name="prediction_bets")
    op.drop_table("prediction_bets")
    op.drop_index("idx_predictions_language", table_name="predictions")
    op.drop_index("idx_predictions_match_id", table_name="predictions")
    op.drop_table("predictions")
    op.drop_index("idx_matches_sport", table_name="matches")
    op.drop_index("idx_matches_match_date", table_name="matches")
    op.drop_index("idx_matches_match_key", table_name="matches")
    op.drop_table("matches")
    op.drop_table("sources")
