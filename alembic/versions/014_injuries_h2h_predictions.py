"""MatchInjury, MatchH2H, MatchApiPrediction tables + fetched_at flags on Match.

Revision ID: 014
Revises: 013
Create Date: 2026-06-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Флаги на матче ---
    op.add_column(
        "matches",
        sa.Column("injuries_fetched_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "matches",
        sa.Column("h2h_fetched_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "matches",
        sa.Column("api_prediction_fetched_at", sa.DateTime(timezone=True), nullable=True),
    )

    # --- Травмы / дисквалификации ---
    op.create_table(
        "match_injuries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "match_id",
            sa.Integer(),
            sa.ForeignKey("matches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "team_id",
            sa.Integer(),
            sa.ForeignKey("teams.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("team_name", sa.String(150), nullable=True),
        sa.Column("side", sa.String(10), nullable=True),        # home | away
        sa.Column("player_name", sa.String(150), nullable=False),
        sa.Column("player_id_ext", sa.String(20), nullable=True),
        sa.Column("position", sa.String(50), nullable=True),
        sa.Column("injury_type", sa.String(100), nullable=True),
        sa.Column("reason", sa.String(200), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("idx_match_injuries_match_id", "match_injuries", ["match_id"])

    # --- H2H (последние N матчей между двумя командами) ---
    op.create_table(
        "match_h2h",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "match_id",
            sa.Integer(),
            sa.ForeignKey("matches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("fixture_external_id", sa.String(30), nullable=False),
        sa.Column("match_date", sa.Date(), nullable=True),
        sa.Column("home_team", sa.String(150), nullable=True),
        sa.Column("away_team", sa.String(150), nullable=True),
        sa.Column("score_home", sa.SmallInteger(), nullable=True),
        sa.Column("score_away", sa.SmallInteger(), nullable=True),
        sa.Column("competition_name", sa.String(150), nullable=True),
        sa.Column("status", sa.String(20), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("match_id", "fixture_external_id", name="uq_h2h_match_fixture"),
    )
    op.create_index("idx_match_h2h_match_id", "match_h2h", ["match_id"])

    # --- Прогноз API-Football (/predictions) ---
    op.create_table(
        "match_api_predictions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "match_id",
            sa.Integer(),
            sa.ForeignKey("matches.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("winner_team", sa.String(150), nullable=True),
        sa.Column("winner_comment", sa.String(300), nullable=True),
        sa.Column("percent_home", sa.SmallInteger(), nullable=True),
        sa.Column("percent_draw", sa.SmallInteger(), nullable=True),
        sa.Column("percent_away", sa.SmallInteger(), nullable=True),
        sa.Column("goals_home", sa.String(20), nullable=True),
        sa.Column("goals_away", sa.String(20), nullable=True),
        sa.Column("advice", sa.Text(), nullable=True),
        sa.Column("form_home", sa.String(10), nullable=True),   # WWDLL
        sa.Column("form_away", sa.String(10), nullable=True),
        sa.Column("raw_json", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_match_api_predictions_match_id", "match_api_predictions", ["match_id"]
    )


def downgrade() -> None:
    op.drop_index("idx_match_api_predictions_match_id", "match_api_predictions")
    op.drop_table("match_api_predictions")
    op.drop_index("idx_match_h2h_match_id", "match_h2h")
    op.drop_table("match_h2h")
    op.drop_index("idx_match_injuries_match_id", "match_injuries")
    op.drop_table("match_injuries")
    op.drop_column("matches", "api_prediction_fetched_at")
    op.drop_column("matches", "h2h_fetched_at")
    op.drop_column("matches", "injuries_fetched_at")
