"""Competition tracking flags, api_quota_snapshots, odds_sync_log.

Revision ID: 013
Revises: 012
Create Date: 2026-06-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "competitions",
        sa.Column("is_tracked", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "competitions",
        sa.Column("sync_odds", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "competitions",
        sa.Column("sync_stats", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "competitions",
        sa.Column("sync_lineups", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column("competitions", sa.Column("odds_markets", sa.Text(), nullable=True))
    op.add_column("competitions", sa.Column("odds_days_ahead", sa.Integer(), nullable=True))

    op.create_table(
        "api_quota_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("requests_remaining", sa.Integer(), nullable=True),
        sa.Column("requests_used", sa.Integer(), nullable=True),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_quota_provider_time",
        "api_quota_snapshots",
        ["provider", "recorded_at"],
    )

    op.create_table(
        "odds_sync_log",
        sa.Column("sport_key", sa.String(length=80), primary_key=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("odds_sync_log")
    op.drop_index("idx_quota_provider_time", table_name="api_quota_snapshots")
    op.drop_table("api_quota_snapshots")
    for col in (
        "odds_days_ahead",
        "odds_markets",
        "sync_lineups",
        "sync_stats",
        "sync_odds",
        "is_tracked",
    ):
        op.drop_column("competitions", col)
