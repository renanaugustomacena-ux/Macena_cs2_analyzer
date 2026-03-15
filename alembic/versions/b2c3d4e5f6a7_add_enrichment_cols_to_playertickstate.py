"""add_enrichment_cols_to_playertickstate

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-12 18:00:00.000000

Safe migration: ADD COLUMN only. No destructive operations.
Adds 7 enrichment columns to playertickstate (round context, alive counts,
economy, map identity). Idempotent: columns may already exist from prior
manual ALTER TABLE operations.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    """Check if a column already exists (idempotent guard)."""
    conn = op.get_bind()
    result = conn.execute(sa.text(f"PRAGMA table_info({table})"))
    return any(row[1] == column for row in result)


def upgrade() -> None:
    """Add enrichment columns to playertickstate if not already present."""
    columns = [
        ("round_number", sa.Integer(), "1"),
        ("time_in_round", sa.Float(), "0.0"),
        ("bomb_planted", sa.Boolean(), "0"),
        ("teammates_alive", sa.Integer(), "4"),
        ("enemies_alive", sa.Integer(), "5"),
        ("team_economy", sa.Integer(), "0"),
        ("map_name", sa.String(), "unknown"),
    ]

    for col_name, col_type, default_val in columns:
        if not _column_exists("playertickstate", col_name):
            op.add_column(
                "playertickstate",
                sa.Column(
                    col_name, col_type, nullable=True, server_default=default_val
                ),
            )


def downgrade() -> None:
    """Remove enrichment columns from playertickstate."""
    columns = [
        "map_name",
        "team_economy",
        "enemies_alive",
        "teammates_alive",
        "bomb_planted",
        "time_in_round",
        "round_number",
    ]
    for col_name in columns:
        if _column_exists("playertickstate", col_name):
            op.drop_column("playertickstate", col_name)
