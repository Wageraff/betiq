"""Widen competitions.country_code for API-Football region codes (e.g. GB-NIR).

Revision ID: 012
Revises: 011
Create Date: 2026-06-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "competitions",
        "country_code",
        existing_type=sa.String(length=5),
        type_=sa.String(length=16),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "competitions",
        "country_code",
        existing_type=sa.String(length=16),
        type_=sa.String(length=5),
        existing_nullable=True,
    )
