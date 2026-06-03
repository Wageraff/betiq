"""Point legalbet source diagnose URL at football section.

Revision ID: 003
Revises: 002
Create Date: 2026-06-03

"""
from typing import Sequence, Union

from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE sources
        SET category_url = '/ponturi/sportul-fotbal/'
        WHERE scraper_module = 'legalbet'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE sources
        SET category_url = '/ponturi/'
        WHERE scraper_module = 'legalbet'
        """
    )
