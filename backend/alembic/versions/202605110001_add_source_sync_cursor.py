"""add source sync cursor

Revision ID: 202605110001
Revises: 202605090002
Create Date: 2026-05-11 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "202605110001"
down_revision = "202605090002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("auction_source_states", sa.Column("sync_cursor", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column("auction_source_states", "sync_cursor")
