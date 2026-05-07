"""grid foundation tables

Revision ID: 202605070001
Revises: 202604280008
Create Date: 2026-05-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "202605070001"
down_revision: Union[str, None] = "202604280008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "grid_revisions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.String(length=128), nullable=False),
        sa.Column("table_id", sa.String(length=128), nullable=False),
        sa.Column("dataset_version", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "table_id", name="uq_grid_revisions_workspace_table"),
    )
    op.create_index(op.f("ix_grid_revisions_table_id"), "grid_revisions", ["table_id"])
    op.create_index(op.f("ix_grid_revisions_updated_at"), "grid_revisions", ["updated_at"])

    op.create_table(
        "grid_change_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.String(length=128), nullable=False),
        sa.Column("table_id", sa.String(length=128), nullable=False),
        sa.Column("dataset_version", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("row_id", sa.String(length=255), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_grid_change_events_workspace_table_version"),
        "grid_change_events",
        ["workspace_id", "table_id", "dataset_version"],
    )
    op.create_index(
        op.f("ix_grid_change_events_table_version"),
        "grid_change_events",
        ["table_id", "dataset_version"],
    )
    op.create_index(op.f("ix_grid_change_events_created_at"), "grid_change_events", ["created_at"])

    op.create_table(
        "grid_operations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", sa.String(length=128), nullable=False),
        sa.Column("table_id", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=True),
        sa.Column("session_id", sa.String(length=255), nullable=True),
        sa.Column("operation_type", sa.String(length=64), nullable=False),
        sa.Column("base_version", sa.BigInteger(), nullable=True),
        sa.Column("resulting_version", sa.BigInteger(), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("undo_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("redo_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_grid_operations_workspace_table_user_session_created"),
        "grid_operations",
        ["workspace_id", "table_id", "user_id", "session_id", "created_at"],
    )
    op.create_index(op.f("ix_grid_operations_table_created"), "grid_operations", ["table_id", "created_at"])
    op.create_index(op.f("ix_grid_operations_operation_type"), "grid_operations", ["operation_type"])


def downgrade() -> None:
    op.drop_index(op.f("ix_grid_operations_operation_type"), table_name="grid_operations")
    op.drop_index(op.f("ix_grid_operations_table_created"), table_name="grid_operations")
    op.drop_index(op.f("ix_grid_operations_workspace_table_user_session_created"), table_name="grid_operations")
    op.drop_table("grid_operations")

    op.drop_index(op.f("ix_grid_change_events_created_at"), table_name="grid_change_events")
    op.drop_index(op.f("ix_grid_change_events_table_version"), table_name="grid_change_events")
    op.drop_index(op.f("ix_grid_change_events_workspace_table_version"), table_name="grid_change_events")
    op.drop_table("grid_change_events")

    op.drop_index(op.f("ix_grid_revisions_updated_at"), table_name="grid_revisions")
    op.drop_index(op.f("ix_grid_revisions_table_id"), table_name="grid_revisions")
    op.drop_table("grid_revisions")
