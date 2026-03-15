"""add_data_quality_to_playermatchstats

Revision ID: a1b2c3d4e5f6
Revises: 3c6ecb5fe20e
Create Date: 2026-03-12 12:00:00.000000

Safe migration: ADD COLUMN only. No destructive operations.
Adds data_quality column to playermatchstats (C-04: track parse completeness).
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "3c6ecb5fe20e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    """Check if a column already exists (idempotent guard)."""
    conn = op.get_bind()
    result = conn.execute(sa.text(f"PRAGMA table_info({table})"))
    return any(row[1] == column for row in result)


def upgrade() -> None:
    """Add data_quality column if not already present."""
    if not _column_exists("playermatchstats", "data_quality"):
        op.add_column(
            "playermatchstats",
            sa.Column("data_quality", sa.String(), nullable=False, server_default="partial"),
        )


def downgrade() -> None:
    """Remove data_quality column."""
    op.drop_column("playermatchstats", "data_quality")
