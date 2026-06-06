"""API-Football + The Odds API integration schema.

Revision ID: 011
Revises: 010
Create Date: 2026-06-04

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 011 — teams
    op.add_column("teams", sa.Column("logo_url", sa.String(length=500), nullable=True))
    op.add_column(
        "teams",
        sa.Column("logo_fetched_at", sa.DateTime(timezone=True), nullable=True),
    )

    # 012 — competitions
    op.create_table(
        "competitions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("sport", sa.String(length=50), nullable=False),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column("country_code", sa.String(length=5), nullable=True),
        sa.Column("logo_url", sa.String(length=500), nullable=True),
        sa.Column("flag_url", sa.String(length=500), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        "CREATE UNIQUE INDEX idx_competitions_name_sport "
        "ON competitions (lower(name), sport)"
    )

    op.create_table(
        "competition_external_ids",
        sa.Column("competition_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("external_id", sa.String(length=100), nullable=False),
        sa.Column("external_name", sa.String(length=200), nullable=True),
        sa.Column("season", sa.String(length=10), nullable=True),
        sa.ForeignKeyConstraint(
            ["competition_id"], ["competitions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("competition_id", "provider"),
    )

    op.add_column("matches", sa.Column("competition_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_matches_competition_id",
        "matches",
        "competitions",
        ["competition_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("idx_matches_competition_id", "matches", ["competition_id"])

    # 013 — match external ids
    op.create_table(
        "match_external_ids",
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("external_id", sa.String(length=100), nullable=False),
        sa.Column(
            "linked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("link_method", sa.String(length=20), server_default="auto"),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("match_id", "provider"),
    )
    op.create_index(
        "idx_match_ext_provider_id",
        "match_external_ids",
        ["provider", "external_id"],
    )

    # 014 — team external ids
    op.create_table(
        "team_external_ids",
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("external_id", sa.String(length=100), nullable=False),
        sa.Column("external_name", sa.String(length=200), nullable=True),
        sa.Column("verified", sa.Boolean(), server_default="false", nullable=True),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("team_id", "provider"),
    )

    # 015 — matches extension
    op.add_column("matches", sa.Column("status", sa.String(length=20), nullable=True))
    op.add_column("matches", sa.Column("venue_name", sa.String(length=200), nullable=True))
    op.add_column("matches", sa.Column("venue_city", sa.String(length=100), nullable=True))
    op.add_column("matches", sa.Column("season", sa.String(length=10), nullable=True))
    op.add_column("matches", sa.Column("round", sa.String(length=50), nullable=True))
    op.add_column("matches", sa.Column("score_home", sa.SmallInteger(), nullable=True))
    op.add_column("matches", sa.Column("score_away", sa.SmallInteger(), nullable=True))
    op.add_column("matches", sa.Column("score_ht_home", sa.SmallInteger(), nullable=True))
    op.add_column("matches", sa.Column("score_ht_away", sa.SmallInteger(), nullable=True))
    op.add_column(
        "matches",
        sa.Column("stats_fetched_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "matches",
        sa.Column("odds_fetched_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_matches_status", "matches", ["status"])

    # 016 — match_stats
    op.create_table(
        "match_stats",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=True),
        sa.Column("side", sa.String(length=5), nullable=False),
        sa.Column("half", sa.String(length=5), server_default="full", nullable=True),
        sa.Column("shots_on_goal", sa.SmallInteger(), nullable=True),
        sa.Column("shots_off_goal", sa.SmallInteger(), nullable=True),
        sa.Column("shots_total", sa.SmallInteger(), nullable=True),
        sa.Column("shots_blocked", sa.SmallInteger(), nullable=True),
        sa.Column("shots_insidebox", sa.SmallInteger(), nullable=True),
        sa.Column("shots_outsidebox", sa.SmallInteger(), nullable=True),
        sa.Column("corners", sa.SmallInteger(), nullable=True),
        sa.Column("fouls", sa.SmallInteger(), nullable=True),
        sa.Column("yellow_cards", sa.SmallInteger(), nullable=True),
        sa.Column("red_cards", sa.SmallInteger(), nullable=True),
        sa.Column("offsides", sa.SmallInteger(), nullable=True),
        sa.Column("possession", sa.SmallInteger(), nullable=True),
        sa.Column("passes_total", sa.SmallInteger(), nullable=True),
        sa.Column("passes_accurate", sa.SmallInteger(), nullable=True),
        sa.Column("goalkeeper_saves", sa.SmallInteger(), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("match_id", "side", "half", name="uq_match_stats_side_half"),
    )
    op.create_index("idx_match_stats_match_id", "match_stats", ["match_id"])
    op.create_index("idx_match_stats_team_id", "match_stats", ["team_id"])

    # 017 — team_form
    op.create_table(
        "team_form",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("fixture_external_id", sa.String(length=50), nullable=True),
        sa.Column("match_date", sa.Date(), nullable=False),
        sa.Column("opponent_name", sa.String(length=150), nullable=True),
        sa.Column("opponent_id", sa.Integer(), nullable=True),
        sa.Column("is_home", sa.Boolean(), nullable=True),
        sa.Column("result", sa.CHAR(length=1), nullable=True),
        sa.Column("goals_scored", sa.SmallInteger(), nullable=True),
        sa.Column("goals_conceded", sa.SmallInteger(), nullable=True),
        sa.Column("corners_for", sa.SmallInteger(), nullable=True),
        sa.Column("corners_against", sa.SmallInteger(), nullable=True),
        sa.Column("yellow_cards", sa.SmallInteger(), nullable=True),
        sa.Column("competition_name", sa.String(length=150), nullable=True),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["opponent_id"], ["teams.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_id", "fixture_external_id", name="uq_team_form_fixture"),
    )
    op.create_index("idx_team_form_team_date", "team_form", ["team_id", "match_date"])

    # 018 — match_lineups
    op.create_table(
        "match_lineups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=True),
        sa.Column("side", sa.String(length=5), nullable=True),
        sa.Column("formation", sa.String(length=20), nullable=True),
        sa.Column("coach_name", sa.String(length=150), nullable=True),
        sa.Column("coach_photo_url", sa.String(length=500), nullable=True),
        sa.Column("lineup_json", JSONB(), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("match_id", "side", name="uq_match_lineups_side"),
    )

    # 019 — match_odds
    op.create_table(
        "match_odds",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("sport", sa.String(length=50), nullable=False),
        sa.Column("bookmaker", sa.String(length=80), nullable=False),
        sa.Column("market", sa.String(length=80), nullable=False),
        sa.Column("outcome", sa.String(length=100), nullable=False),
        sa.Column("odds", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("point", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("is_live", sa.Boolean(), server_default="false", nullable=True),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "match_id",
            "bookmaker",
            "market",
            "outcome",
            "is_live",
            name="uq_match_odds_key",
        ),
    )
    op.create_index("idx_match_odds_match_id", "match_odds", ["match_id"])
    op.create_index("idx_match_odds_sport", "match_odds", ["sport"])
    op.create_index("idx_match_odds_bookmaker", "match_odds", ["bookmaker"])
    op.create_index("idx_match_odds_market", "match_odds", ["market"])

    # 020 — odds_history
    op.create_table(
        "odds_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("bookmaker", sa.String(length=80), nullable=False),
        sa.Column("market", sa.String(length=80), nullable=False),
        sa.Column("outcome", sa.String(length=100), nullable=False),
        sa.Column("odds_prev", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("odds_curr", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("movement_pct", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("direction", sa.CHAR(length=4), nullable=True),
        sa.Column("is_significant", sa.Boolean(), server_default="false", nullable=True),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_odds_history_match_id", "odds_history", ["match_id"])
    op.create_index(
        "idx_odds_history_significant",
        "odds_history",
        ["is_significant", "recorded_at"],
    )

    # 021 — ai_chat_cache
    op.create_table(
        "ai_chat_cache",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cache_key", sa.String(length=300), nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=True),
        sa.Column("question_type", sa.String(length=50), nullable=False),
        sa.Column("language", sa.String(length=10), nullable=False),
        sa.Column("response_text", sa.Text(), nullable=False),
        sa.Column("tokens_input", sa.Integer(), nullable=True),
        sa.Column("tokens_output", sa.Integer(), nullable=True),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hit_count", sa.Integer(), server_default="0", nullable=True),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cache_key"),
    )
    op.create_index("idx_ai_cache_key", "ai_chat_cache", ["cache_key"])
    op.create_index("idx_ai_cache_expires", "ai_chat_cache", ["expires_at"])
    op.create_index("idx_ai_cache_match", "ai_chat_cache", ["match_id"])


def downgrade() -> None:
    op.drop_table("ai_chat_cache")
    op.drop_table("odds_history")
    op.drop_table("match_odds")
    op.drop_table("match_lineups")
    op.drop_table("team_form")
    op.drop_table("match_stats")
    op.drop_index("idx_matches_status", table_name="matches")
    for col in (
        "odds_fetched_at",
        "stats_fetched_at",
        "score_ht_away",
        "score_ht_home",
        "score_away",
        "score_home",
        "round",
        "season",
        "venue_city",
        "venue_name",
        "status",
    ):
        op.drop_column("matches", col)
    op.drop_table("team_external_ids")
    op.drop_table("match_external_ids")
    op.drop_constraint("fk_matches_competition_id", "matches", type_="foreignkey")
    op.drop_index("idx_matches_competition_id", table_name="matches")
    op.drop_column("matches", "competition_id")
    op.drop_table("competition_external_ids")
    op.drop_table("competitions")
    op.drop_column("teams", "logo_fetched_at")
    op.drop_column("teams", "logo_url")
