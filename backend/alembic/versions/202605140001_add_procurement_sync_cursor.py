"""add procurement sync cursor

Revision ID: 202605140001
Revises: 202605130015
Create Date: 2026-05-14 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "202605140001"
down_revision = "202605130015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "procurement_source_sync_states",
        sa.Column(
            "cursor_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "procurement_source_sync_states",
        sa.Column("cursor_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f("ix_procurement_source_sync_states_cursor_updated_at"),
        "procurement_source_sync_states",
        ["cursor_updated_at"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_procurement_source_sync_states_cursor_updated_at"), table_name="procurement_source_sync_states")
    op.drop_column("procurement_source_sync_states", "cursor_updated_at")
    op.drop_column("procurement_source_sync_states", "cursor_payload")
