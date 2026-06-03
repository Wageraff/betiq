"""Seed legalbet.ru source.

Revision ID: 004
Revises: 003
Create Date: 2026-06-02

"""
from typing import Sequence, Union

from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO sources (name, base_url, category_url, language, geo, is_active, scraper_module)
        SELECT 'legalbet.ru', 'https://legalbet.ru', '/tips/sport-futbol/', 'ru', 'RU', true, 'legalbet_ru'
        WHERE NOT EXISTS (SELECT 1 FROM sources WHERE scraper_module = 'legalbet_ru')
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM sources
        WHERE scraper_module = 'legalbet_ru'
        """
    )
