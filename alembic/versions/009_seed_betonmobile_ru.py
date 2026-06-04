"""Seed betonmobile.ru source.

Revision ID: 009
Revises: 008
Create Date: 2026-06-04

"""
from typing import Sequence, Union

from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO sources (name, base_url, category_url, language, geo, is_active, scraper_module)
        SELECT 'betonmobile.ru', 'https://betonmobile.ru', '/prognozy/prognozy-na-futbol', 'ru', 'RU', true, 'betonmobile_ru'
        WHERE NOT EXISTS (SELECT 1 FROM sources WHERE scraper_module = 'betonmobile_ru')
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM sources
        WHERE scraper_module = 'betonmobile_ru'
        """
    )
