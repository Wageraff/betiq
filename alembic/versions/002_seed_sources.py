"""Seed beturi and pontulzilei sources.

Revision ID: 002
Revises: 001
Create Date: 2026-06-02

"""
from typing import Sequence, Union

from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO sources (name, base_url, category_url, language, geo, is_active, scraper_module)
        SELECT 'beturi.ro', 'https://beturi.ro', '/ponturi-pariuri/', 'ro', 'RO', true, 'beturi'
        WHERE NOT EXISTS (SELECT 1 FROM sources WHERE scraper_module = 'beturi')
        """
    )
    op.execute(
        """
        INSERT INTO sources (name, base_url, category_url, language, geo, is_active, scraper_module)
        SELECT 'pontul-zilei.com', 'https://www.pontul-zilei.com', '/category/ponturi-pariuri/', 'ro', 'RO', true, 'pontulzilei'
        WHERE NOT EXISTS (SELECT 1 FROM sources WHERE scraper_module = 'pontulzilei')
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM sources
        WHERE scraper_module IN ('beturi', 'pontulzilei')
        """
    )
