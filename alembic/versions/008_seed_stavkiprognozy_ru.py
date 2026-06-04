"""Seed stavkiprognozy.ru source.

Revision ID: 008
Revises: 007
Create Date: 2026-06-04

"""
from typing import Sequence, Union

from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO sources (name, base_url, category_url, language, geo, is_active, scraper_module)
        SELECT 'stavkiprognozy.ru', 'https://stavkiprognozy.ru', '/prognozy/football/', 'ru', 'RU', true, 'stavkiprognozy_ru'
        WHERE NOT EXISTS (SELECT 1 FROM sources WHERE scraper_module = 'stavkiprognozy_ru')
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM sources
        WHERE scraper_module = 'stavkiprognozy_ru'
        """
    )
