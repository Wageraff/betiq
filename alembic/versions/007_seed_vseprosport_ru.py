"""Seed vseprosport.ru source.

Revision ID: 007
Revises: 006
Create Date: 2026-06-04

"""
from typing import Sequence, Union

from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO sources (name, base_url, category_url, language, geo, is_active, scraper_module)
        SELECT 'vseprosport.ru', 'https://www.vseprosport.ru', '/news/football', 'ru', 'RU', true, 'vseprosport_ru'
        WHERE NOT EXISTS (SELECT 1 FROM sources WHERE scraper_module = 'vseprosport_ru')
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM sources
        WHERE scraper_module = 'vseprosport_ru'
        """
    )
