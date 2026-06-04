"""Teams catalog and match FKs.

Revision ID: 005
Revises: 004
Create Date: 2026-06-04

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "teams",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("normalized_key", sa.String(length=150), nullable=False),
        sa.Column("display_name", sa.String(length=150), nullable=False),
        sa.Column("sport", sa.String(length=50), nullable=True),
        sa.Column("logo_path", sa.String(length=500), nullable=True),
        sa.Column("aliases", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("normalized_key"),
    )
    op.create_index("idx_teams_sport", "teams", ["sport"], unique=False)

    op.add_column("matches", sa.Column("team_home_id", sa.Integer(), nullable=True))
    op.add_column("matches", sa.Column("team_away_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_matches_team_home_id", "matches", "teams", ["team_home_id"], ["id"], ondelete="SET NULL"
    )
    op.create_foreign_key(
        "fk_matches_team_away_id", "matches", "teams", ["team_away_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("idx_matches_team_home_id", "matches", ["team_home_id"], unique=False)
    op.create_index("idx_matches_team_away_id", "matches", ["team_away_id"], unique=False)

    # Backfill teams from existing matches (normalized_key = lower alphanumeric)
    op.execute(
        """
        INSERT INTO teams (normalized_key, display_name, sport)
        SELECT DISTINCT nk, dn, sp FROM (
            SELECT LOWER(REGEXP_REPLACE(REGEXP_REPLACE(team_home, '[^a-zA-Z0-9]', '', 'g'), '\\s+', '', 'g')) AS nk,
                   team_home AS dn, sport AS sp FROM matches WHERE team_home IS NOT NULL
            UNION
            SELECT LOWER(REGEXP_REPLACE(REGEXP_REPLACE(team_away, '[^a-zA-Z0-9]', '', 'g'), '\\s+', '', 'g')),
                   team_away, sport FROM matches WHERE team_away IS NOT NULL
        ) sub
        WHERE nk <> '' AND NOT EXISTS (SELECT 1 FROM teams t WHERE t.normalized_key = sub.nk)
        """
    )
    op.execute(
        """
        UPDATE matches m SET team_home_id = t.id
        FROM teams t
        WHERE t.normalized_key = LOWER(REGEXP_REPLACE(REGEXP_REPLACE(m.team_home, '[^a-zA-Z0-9]', '', 'g'), '\\s+', '', 'g'))
        """
    )
    op.execute(
        """
        UPDATE matches m SET team_away_id = t.id
        FROM teams t
        WHERE t.normalized_key = LOWER(REGEXP_REPLACE(REGEXP_REPLACE(m.team_away, '[^a-zA-Z0-9]', '', 'g'), '\\s+', '', 'g'))
        """
    )


def downgrade() -> None:
    op.drop_constraint("fk_matches_team_away_id", "matches", type_="foreignkey")
    op.drop_constraint("fk_matches_team_home_id", "matches", type_="foreignkey")
    op.drop_index("idx_matches_team_away_id", table_name="matches")
    op.drop_index("idx_matches_team_home_id", table_name="matches")
    op.drop_column("matches", "team_away_id")
    op.drop_column("matches", "team_home_id")
    op.drop_index("idx_teams_sport", table_name="teams")
    op.drop_table("teams")
