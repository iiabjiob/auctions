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


def _existing_columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _existing_indexes(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return set()
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    table_name = "auction_source_sync_states"
    existing_columns = _existing_columns(table_name)
    existing_indexes = _existing_indexes(table_name)

    columns = {
        "next_page": sa.Column("next_page", sa.Integer(), nullable=True),
        "last_start_page": sa.Column("last_start_page", sa.Integer(), nullable=True),
        "last_window_size": sa.Column("last_window_size", sa.Integer(), nullable=True),
        "last_fetched": sa.Column("last_fetched", sa.Integer(), nullable=True),
    }
    for column_name, column in columns.items():
        if column_name not in existing_columns:
            op.add_column(table_name, column)

    indexes = {
        op.f("ix_auction_source_sync_states_next_page"): ("next_page",),
        op.f("ix_auction_source_sync_states_last_start_page"): ("last_start_page",),
        op.f("ix_auction_source_sync_states_last_window_size"): ("last_window_size",),
        op.f("ix_auction_source_sync_states_last_fetched"): ("last_fetched",),
    }
    for index_name, column_names in indexes.items():
        if index_name not in existing_indexes:
            op.create_index(index_name, table_name, list(column_names))


def downgrade() -> None:
    table_name = "auction_source_sync_states"
    existing_columns = _existing_columns(table_name)
    existing_indexes = _existing_indexes(table_name)

    for index_name in (
        op.f("ix_auction_source_sync_states_last_fetched"),
        op.f("ix_auction_source_sync_states_last_window_size"),
        op.f("ix_auction_source_sync_states_last_start_page"),
        op.f("ix_auction_source_sync_states_next_page"),
    ):
        if index_name in existing_indexes:
            op.drop_index(index_name, table_name=table_name)

    for column_name in ("last_fetched", "last_window_size", "last_start_page", "next_page"):
        if column_name in existing_columns:
            op.drop_column(table_name, column_name)
