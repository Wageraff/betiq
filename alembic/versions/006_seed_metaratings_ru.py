"""Seed metaratings.ru source.

Revision ID: 006
Revises: 005
Create Date: 2026-06-04

"""
from typing import Sequence, Union

from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO sources (name, base_url, category_url, language, geo, is_active, scraper_module)
        SELECT 'metaratings.ru', 'https://metaratings.ru', '/prognozy/futbol/', 'ru', 'RU', true, 'metaratings_ru'
        WHERE NOT EXISTS (SELECT 1 FROM sources WHERE scraper_module = 'metaratings_ru')
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM sources
        WHERE scraper_module = 'metaratings_ru'
        """
    )
