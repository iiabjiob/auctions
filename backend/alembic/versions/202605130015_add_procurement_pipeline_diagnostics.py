"""add procurement pipeline diagnostics

Revision ID: 202605130015
Revises: 202605130014
Create Date: 2026-05-13 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "202605130015"
down_revision = "202605130014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "procurement_source_sync_states",
        sa.Column("source_code", sa.String(length=64), nullable=False),
        sa.Column("last_sync_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_successful_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_result", sa.String(length=32), nullable=True),
        sa.Column("last_sync_error", sa.Text(), nullable=True),
        sa.Column("last_sync_error_code", sa.String(length=64), nullable=True),
        sa.Column("last_sync_fetched", sa.Integer(), nullable=True),
        sa.Column("last_sync_created", sa.Integer(), nullable=True),
        sa.Column("last_sync_updated", sa.Integer(), nullable=True),
        sa.Column("last_sync_unchanged", sa.Integer(), nullable=True),
        sa.Column("last_sync_status_changed", sa.Integer(), nullable=True),
        sa.Column("last_sync_parser_failures", sa.Integer(), nullable=True),
        sa.Column(
            "last_sync_missing_critical_fields",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("parser_version", sa.String(length=64), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["source_code"], ["procurement_source_states.code"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("source_code"),
    )
    for column in (
        "last_sync_started_at",
        "last_sync_completed_at",
        "last_successful_sync_at",
        "last_sync_result",
        "last_sync_error_code",
        "parser_version",
    ):
        op.create_index(op.f(f"ix_procurement_source_sync_states_{column}"), "procurement_source_sync_states", [column])

    op.create_table(
        "procurement_source_sync_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_code", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", sa.String(length=32), nullable=False),
        sa.Column("fetched_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("updated_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("unchanged_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status_changed_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("parser_failure_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "missing_critical_fields",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("parser_version", sa.String(length=64), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["source_code"], ["procurement_source_states.code"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("source_code", "started_at", "completed_at", "result", "parser_version", "error_code"):
        op.create_index(op.f(f"ix_procurement_source_sync_runs_{column}"), "procurement_source_sync_runs", [column])


def downgrade() -> None:
    for column in ("error_code", "parser_version", "result", "completed_at", "started_at", "source_code"):
        op.drop_index(op.f(f"ix_procurement_source_sync_runs_{column}"), table_name="procurement_source_sync_runs")
    op.drop_table("procurement_source_sync_runs")
    for column in (
        "parser_version",
        "last_sync_error_code",
        "last_sync_result",
        "last_successful_sync_at",
        "last_sync_completed_at",
        "last_sync_started_at",
    ):
        op.drop_index(op.f(f"ix_procurement_source_sync_states_{column}"), table_name="procurement_source_sync_states")
    op.drop_table("procurement_source_sync_states")
