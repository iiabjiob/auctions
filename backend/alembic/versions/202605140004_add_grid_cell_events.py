"""add grid cell events

Revision ID: 202605140004
Revises: 202605140003
Create Date: 2026-05-14 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "202605140004"
down_revision = "202605140003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "grid_cell_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("operation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", sa.String(length=128), nullable=False),
        sa.Column("table_id", sa.String(length=128), nullable=False),
        sa.Column("row_id", sa.String(length=255), nullable=False),
        sa.Column("column_id", sa.String(length=128), nullable=False),
        sa.Column("before_value", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("after_value", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["operation_id"], ["grid_operations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_grid_cell_events_operation_id"), "grid_cell_events", ["operation_id"])
    op.create_index(
        op.f("ix_grid_cell_events_workspace_table_operation"),
        "grid_cell_events",
        ["workspace_id", "table_id", "operation_id"],
    )
    op.create_index(
        op.f("ix_grid_cell_events_workspace_table_row"),
        "grid_cell_events",
        ["workspace_id", "table_id", "row_id"],
    )
    op.create_index(op.f("ix_grid_cell_events_created_at"), "grid_cell_events", ["created_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_grid_cell_events_created_at"), table_name="grid_cell_events")
    op.drop_index(op.f("ix_grid_cell_events_workspace_table_row"), table_name="grid_cell_events")
    op.drop_index(op.f("ix_grid_cell_events_workspace_table_operation"), table_name="grid_cell_events")
    op.drop_index(op.f("ix_grid_cell_events_operation_id"), table_name="grid_cell_events")
    op.drop_table("grid_cell_events")
