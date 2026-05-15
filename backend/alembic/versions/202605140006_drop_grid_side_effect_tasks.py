"""drop grid side effect tasks

Revision ID: 202605140006
Revises: 202605140005
Create Date: 2026-05-14 00:10:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "202605140006"
down_revision = "202605140005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index(op.f("ix_grid_side_effect_tasks_created_at"), table_name="grid_side_effect_tasks")
    op.drop_index(op.f("ix_grid_side_effect_tasks_workspace_table_row"), table_name="grid_side_effect_tasks")
    op.drop_index(op.f("ix_grid_side_effect_tasks_operation_id"), table_name="grid_side_effect_tasks")
    op.drop_index(op.f("ix_grid_side_effect_tasks_status_next_attempt"), table_name="grid_side_effect_tasks")
    op.drop_table("grid_side_effect_tasks")


def downgrade() -> None:
    op.create_table(
        "grid_side_effect_tasks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("operation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", sa.String(length=128), nullable=False),
        sa.Column("table_id", sa.String(length=128), nullable=False),
        sa.Column("row_id", sa.String(length=255), nullable=False),
        sa.Column("effect_type", sa.String(length=64), nullable=False),
        sa.Column("trigger_type", sa.String(length=32), server_default=sa.text("'commit'"), nullable=False),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default=sa.text("3"), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("claimed_by", sa.String(length=128), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["operation_id"], ["grid_operations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "operation_id",
            "row_id",
            "effect_type",
            "trigger_type",
            name="uq_grid_side_effect_tasks_operation_row_effect_trigger",
        ),
    )
    op.create_index(op.f("ix_grid_side_effect_tasks_created_at"), "grid_side_effect_tasks", ["created_at"])
    op.create_index(op.f("ix_grid_side_effect_tasks_operation_id"), "grid_side_effect_tasks", ["operation_id"])
    op.create_index(
        op.f("ix_grid_side_effect_tasks_status_next_attempt"),
        "grid_side_effect_tasks",
        ["status", "next_attempt_at"],
    )
    op.create_index(
        op.f("ix_grid_side_effect_tasks_workspace_table_row"),
        "grid_side_effect_tasks",
        ["workspace_id", "table_id", "row_id"],
    )
