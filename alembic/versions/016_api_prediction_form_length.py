"""Widen match_api_predictions form columns (API returns long strings).

Revision ID: 016
Revises: 015
Create Date: 2026-06-08

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "match_api_predictions",
        "form_home",
        existing_type=sa.String(10),
        type_=sa.String(16),
        existing_nullable=True,
    )
    op.alter_column(
        "match_api_predictions",
        "form_away",
        existing_type=sa.String(10),
        type_=sa.String(16),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "match_api_predictions",
        "form_away",
        existing_type=sa.String(16),
        type_=sa.String(10),
        existing_nullable=True,
    )
    op.alter_column(
        "match_api_predictions",
        "form_home",
        existing_type=sa.String(16),
        type_=sa.String(10),
        existing_nullable=True,
    )
