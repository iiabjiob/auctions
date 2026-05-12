"""add auction source sync page columns

Revision ID: 202605120005
Revises: 202605120004
Create Date: 2026-05-12 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202605120005"
down_revision = "202605120004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("auction_source_sync_states", sa.Column("next_page", sa.Integer(), nullable=True))
    op.add_column("auction_source_sync_states", sa.Column("last_start_page", sa.Integer(), nullable=True))
    op.add_column("auction_source_sync_states", sa.Column("last_window_size", sa.Integer(), nullable=True))
    op.add_column("auction_source_sync_states", sa.Column("last_fetched", sa.Integer(), nullable=True))

    op.create_index(
        op.f("ix_auction_source_sync_states_next_page"),
        "auction_source_sync_states",
        ["next_page"],
    )
    op.create_index(
        op.f("ix_auction_source_sync_states_last_start_page"),
        "auction_source_sync_states",
        ["last_start_page"],
    )
    op.create_index(
        op.f("ix_auction_source_sync_states_last_window_size"),
        "auction_source_sync_states",
        ["last_window_size"],
    )
    op.create_index(
        op.f("ix_auction_source_sync_states_last_fetched"),
        "auction_source_sync_states",
        ["last_fetched"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_auction_source_sync_states_last_fetched"), table_name="auction_source_sync_states")
    op.drop_index(op.f("ix_auction_source_sync_states_last_window_size"), table_name="auction_source_sync_states")
    op.drop_index(op.f("ix_auction_source_sync_states_last_start_page"), table_name="auction_source_sync_states")
    op.drop_index(op.f("ix_auction_source_sync_states_next_page"), table_name="auction_source_sync_states")
    op.drop_column("auction_source_sync_states", "last_fetched")
    op.drop_column("auction_source_sync_states", "last_window_size")
    op.drop_column("auction_source_sync_states", "last_start_page")
    op.drop_column("auction_source_sync_states", "next_page")
