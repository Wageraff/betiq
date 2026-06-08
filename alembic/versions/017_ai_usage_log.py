"""Log Claude API usage per request.

Revision ID: 017
Revises: 016
Create Date: 2026-06-08

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_usage_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("match_id", sa.Integer(), sa.ForeignKey("matches.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source", sa.String(32), nullable=False, server_default="summary"),
        sa.Column("model", sa.String(80), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("idx_ai_usage_log_created_at", "ai_usage_log", ["created_at"])
    op.create_index("idx_ai_usage_log_match_id", "ai_usage_log", ["match_id"])


def downgrade() -> None:
    op.drop_index("idx_ai_usage_log_match_id", "ai_usage_log")
    op.drop_index("idx_ai_usage_log_created_at", "ai_usage_log")
    op.drop_table("ai_usage_log")
