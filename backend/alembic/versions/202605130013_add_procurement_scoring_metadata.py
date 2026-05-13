"""add procurement scoring metadata

Revision ID: 202605130013
Revises: 202605130012
Create Date: 2026-05-13 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202605130013"
down_revision = "202605130012"
branch_labels = None
depends_on = None


TABLE = "procurement_lot_records"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("scoring_version", sa.String(length=32), nullable=True))
    op.add_column(TABLE, sa.Column("scoring_input_hash", sa.String(length=64), nullable=True))
    op.add_column(TABLE, sa.Column("scored_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f(f"ix_{TABLE}_scoring_version"), TABLE, ["scoring_version"])
    op.create_index(op.f(f"ix_{TABLE}_scored_at"), TABLE, ["scored_at"])


def downgrade() -> None:
    op.drop_index(op.f(f"ix_{TABLE}_scored_at"), table_name=TABLE)
    op.drop_index(op.f(f"ix_{TABLE}_scoring_version"), table_name=TABLE)
    op.drop_column(TABLE, "scored_at")
    op.drop_column(TABLE, "scoring_input_hash")
    op.drop_column(TABLE, "scoring_version")
