"""add procurement calculator payloads

Revision ID: 202605130012
Revises: 202605130011
Create Date: 2026-05-13 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "202605130012"
down_revision = "202605130011"
branch_labels = None
depends_on = None


TABLE = "procurement_lot_records"


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column(
            "calculator_inputs",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        TABLE,
        sa.Column(
            "calculator_scenarios",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column(TABLE, "calculator_scenarios")
    op.drop_column(TABLE, "calculator_inputs")
