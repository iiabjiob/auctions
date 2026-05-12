"""drop auction source state sync cursor

Revision ID: 202605120004
Revises: 202605120003
Create Date: 2026-05-12 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "202605120004"
down_revision = "202605120003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("auction_source_states", "sync_cursor")


def downgrade() -> None:
    op.add_column("auction_source_states", sa.Column("sync_cursor", JSONB(), nullable=True))
