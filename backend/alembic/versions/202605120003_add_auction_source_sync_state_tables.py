"""add auction source sync state tables

Revision ID: 202605120003
Revises: 202605120002
Create Date: 2026-05-12 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202605120003"
down_revision = "202605120002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auction_source_sync_states",
        sa.Column("source_code", sa.String(length=64), sa.ForeignKey("auction_source_states.code"), primary_key=True),
        sa.Column("last_sync_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_sync_not_before", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_sync_not_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_result", sa.String(length=32), nullable=True),
        sa.Column("last_sync_error", sa.Text(), nullable=True),
        sa.Column("last_sync_error_code", sa.String(length=64), nullable=True),
        sa.Column("last_sync_fetched", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        op.f("ix_auction_source_sync_states_last_sync_started_at"),
        "auction_source_sync_states",
        ["last_sync_started_at"],
    )
    op.create_index(
        op.f("ix_auction_source_sync_states_last_sync_completed_at"),
        "auction_source_sync_states",
        ["last_sync_completed_at"],
    )
    op.create_index(
        op.f("ix_auction_source_sync_states_next_sync_not_before"),
        "auction_source_sync_states",
        ["next_sync_not_before"],
    )
    op.create_index(
        op.f("ix_auction_source_sync_states_next_sync_not_after"),
        "auction_source_sync_states",
        ["next_sync_not_after"],
    )
    op.create_index(
        op.f("ix_auction_source_sync_states_last_sync_result"),
        "auction_source_sync_states",
        ["last_sync_result"],
    )
    op.create_index(
        op.f("ix_auction_source_sync_states_last_sync_error_code"),
        "auction_source_sync_states",
        ["last_sync_error_code"],
    )

    op.create_table(
        "auction_source_sync_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source_code", sa.String(length=64), sa.ForeignKey("auction_source_states.code"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", sa.String(length=32), nullable=False),
        sa.Column("fetched_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_sync_not_before", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_sync_not_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        op.f("ix_auction_source_sync_runs_source_code"),
        "auction_source_sync_runs",
        ["source_code"],
    )
    op.create_index(
        op.f("ix_auction_source_sync_runs_started_at"),
        "auction_source_sync_runs",
        ["started_at"],
    )
    op.create_index(
        op.f("ix_auction_source_sync_runs_result"),
        "auction_source_sync_runs",
        ["result"],
    )
    op.create_index(
        op.f("ix_auction_source_sync_runs_completed_at"),
        "auction_source_sync_runs",
        ["completed_at"],
    )
    op.create_index(
        op.f("ix_auction_source_sync_runs_next_sync_not_before"),
        "auction_source_sync_runs",
        ["next_sync_not_before"],
    )
    op.create_index(
        op.f("ix_auction_source_sync_runs_next_sync_not_after"),
        "auction_source_sync_runs",
        ["next_sync_not_after"],
    )
    op.create_index(
        op.f("ix_auction_source_sync_runs_error_code"),
        "auction_source_sync_runs",
        ["error_code"],
    )

    op.execute(
        """
        INSERT INTO auction_source_sync_states (
            source_code,
            last_sync_started_at,
            last_sync_completed_at,
            next_sync_not_before,
            next_sync_not_after,
            last_sync_result,
            last_sync_error,
            last_sync_error_code,
            last_sync_fetched
        )
        SELECT
            code,
            NULLIF(sync_cursor->>'last_sync_started_at', '')::timestamptz,
            NULLIF(sync_cursor->>'last_sync_completed_at', '')::timestamptz,
            NULLIF(sync_cursor->>'next_sync_not_before', '')::timestamptz,
            NULLIF(sync_cursor->>'next_sync_not_after', '')::timestamptz,
            CASE
                WHEN sync_cursor ? 'last_sync_error' THEN 'failed'
                WHEN sync_cursor ? 'last_sync_completed_at' THEN 'success'
                WHEN sync_cursor ? 'last_sync_started_at' THEN 'running'
                ELSE NULL
            END,
            sync_cursor->>'last_sync_error',
            NULL,
            NULLIF(sync_cursor->>'last_fetched', '')::int
        FROM auction_source_states
        WHERE sync_cursor IS NOT NULL
        ON CONFLICT (source_code) DO UPDATE SET
            last_sync_started_at = EXCLUDED.last_sync_started_at,
            last_sync_completed_at = EXCLUDED.last_sync_completed_at,
            next_sync_not_before = EXCLUDED.next_sync_not_before,
            next_sync_not_after = EXCLUDED.next_sync_not_after,
            last_sync_result = EXCLUDED.last_sync_result,
            last_sync_error = EXCLUDED.last_sync_error,
            last_sync_error_code = EXCLUDED.last_sync_error_code,
            last_sync_fetched = EXCLUDED.last_sync_fetched
        """
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_auction_source_sync_runs_error_code"), table_name="auction_source_sync_runs")
    op.drop_index(op.f("ix_auction_source_sync_runs_next_sync_not_after"), table_name="auction_source_sync_runs")
    op.drop_index(op.f("ix_auction_source_sync_runs_next_sync_not_before"), table_name="auction_source_sync_runs")
    op.drop_index(op.f("ix_auction_source_sync_runs_completed_at"), table_name="auction_source_sync_runs")
    op.drop_index(op.f("ix_auction_source_sync_runs_result"), table_name="auction_source_sync_runs")
    op.drop_index(op.f("ix_auction_source_sync_runs_started_at"), table_name="auction_source_sync_runs")
    op.drop_index(op.f("ix_auction_source_sync_runs_source_code"), table_name="auction_source_sync_runs")
    op.drop_table("auction_source_sync_runs")

    op.drop_index(op.f("ix_auction_source_sync_states_last_sync_error_code"), table_name="auction_source_sync_states")
    op.drop_index(op.f("ix_auction_source_sync_states_last_sync_result"), table_name="auction_source_sync_states")
    op.drop_index(op.f("ix_auction_source_sync_states_next_sync_not_after"), table_name="auction_source_sync_states")
    op.drop_index(op.f("ix_auction_source_sync_states_next_sync_not_before"), table_name="auction_source_sync_states")
    op.drop_index(op.f("ix_auction_source_sync_states_last_sync_completed_at"), table_name="auction_source_sync_states")
    op.drop_index(op.f("ix_auction_source_sync_states_last_sync_started_at"), table_name="auction_source_sync_states")
    op.drop_table("auction_source_sync_states")
