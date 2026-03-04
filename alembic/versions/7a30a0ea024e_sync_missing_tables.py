"""Sync_Missing_Tables

Revision ID: 7a30a0ea024e
Revises: f769fbe67229
Create Date: 2026-01-11 01:54:02.121419

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7a30a0ea024e"
down_revision: Union[str, Sequence[str], None] = "f769fbe67229"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema — create CalibrationSnapshot and RoleThresholdRecord tables."""
    op.create_table(
        "calibrationsnapshot",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("calibration_type", sa.String(), nullable=False, index=True),
        sa.Column("parameters_json", sa.String(), nullable=False, server_default="{}"),
        sa.Column("sample_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source", sa.String(), nullable=False, server_default="auto"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        if_not_exists=True,
    )
    op.create_table(
        "rolethresholdrecord",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("stat_name", sa.String(), nullable=False, unique=True, index=True),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source", sa.String(), nullable=False, server_default="unknown"),
        sa.Column("last_updated", sa.DateTime(), nullable=False),
        if_not_exists=True,
    )


def downgrade() -> None:
    """Downgrade schema — drop CalibrationSnapshot and RoleThresholdRecord."""
    op.drop_table("rolethresholdrecord")
    op.drop_table("calibrationsnapshot")
