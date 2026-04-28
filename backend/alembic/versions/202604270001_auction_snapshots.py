"""auction snapshots

Revision ID: 202604270001
Revises: 
Create Date: 2026-04-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "202604270001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "auction_source_states",
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("website", sa.String(length=512), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("code"),
    )
    op.create_table(
        "auction_lot_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_code", sa.String(length=64), nullable=False),
        sa.Column("auction_external_id", sa.String(length=128), nullable=False),
        sa.Column("lot_external_id", sa.String(length=128), nullable=False),
        sa.Column("auction_number", sa.String(length=128), nullable=True),
        sa.Column("lot_number", sa.String(length=128), nullable=True),
        sa.Column("lot_name", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=255), nullable=True),
        sa.Column("initial_price", sa.String(length=128), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_new", sa.Boolean(), nullable=False),
        sa.Column("rating_score", sa.Integer(), nullable=False),
        sa.Column("rating_level", sa.String(length=32), nullable=False),
        sa.Column("datagrid_row", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("normalized_item", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["source_code"], ["auction_source_states.code"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_code", "auction_external_id", "lot_external_id"),
    )
    op.create_index(op.f("ix_auction_lot_records_auction_external_id"), "auction_lot_records", ["auction_external_id"])
    op.create_index(op.f("ix_auction_lot_records_auction_number"), "auction_lot_records", ["auction_number"])
    op.create_index(op.f("ix_auction_lot_records_is_new"), "auction_lot_records", ["is_new"])
    op.create_index(op.f("ix_auction_lot_records_lot_external_id"), "auction_lot_records", ["lot_external_id"])
    op.create_index(op.f("ix_auction_lot_records_rating_score"), "auction_lot_records", ["rating_score"])
    op.create_index(op.f("ix_auction_lot_records_source_code"), "auction_lot_records", ["source_code"])
    op.create_index(op.f("ix_auction_lot_records_status"), "auction_lot_records", ["status"])
    op.create_table(
        "auction_lot_observations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("lot_record_id", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=255), nullable=True),
        sa.Column("datagrid_row", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("normalized_item", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["lot_record_id"], ["auction_lot_records.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_auction_lot_observations_content_hash"), "auction_lot_observations", ["content_hash"])
    op.create_index(op.f("ix_auction_lot_observations_lot_record_id"), "auction_lot_observations", ["lot_record_id"])
    op.create_index(op.f("ix_auction_lot_observations_status"), "auction_lot_observations", ["status"])


def downgrade() -> None:
    op.drop_index(op.f("ix_auction_lot_observations_status"), table_name="auction_lot_observations")
    op.drop_index(op.f("ix_auction_lot_observations_lot_record_id"), table_name="auction_lot_observations")
    op.drop_index(op.f("ix_auction_lot_observations_content_hash"), table_name="auction_lot_observations")
    op.drop_table("auction_lot_observations")
    op.drop_index(op.f("ix_auction_lot_records_status"), table_name="auction_lot_records")
    op.drop_index(op.f("ix_auction_lot_records_source_code"), table_name="auction_lot_records")
    op.drop_index(op.f("ix_auction_lot_records_rating_score"), table_name="auction_lot_records")
    op.drop_index(op.f("ix_auction_lot_records_lot_external_id"), table_name="auction_lot_records")
    op.drop_index(op.f("ix_auction_lot_records_is_new"), table_name="auction_lot_records")
    op.drop_index(op.f("ix_auction_lot_records_auction_number"), table_name="auction_lot_records")
    op.drop_index(op.f("ix_auction_lot_records_auction_external_id"), table_name="auction_lot_records")
    op.drop_table("auction_lot_records")
    op.drop_table("auction_source_states")