"""lot workspace

Revision ID: 202604270002
Revises: 202604270001
Create Date: 2026-04-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "202604270002"
down_revision: Union[str, None] = "202604270001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "auction_lot_detail_caches",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("lot_record_id", sa.Integer(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("lot_detail", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("auction_detail", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("documents", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["lot_record_id"], ["auction_lot_records.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lot_record_id"),
    )
    op.create_index(
        op.f("ix_auction_lot_detail_caches_lot_record_id"),
        "auction_lot_detail_caches",
        ["lot_record_id"],
    )

    op.create_table(
        "auction_lot_work_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("lot_record_id", sa.Integer(), nullable=False),
        sa.Column("decision_status", sa.String(length=64), nullable=True),
        sa.Column("assignee", sa.String(length=255), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("inspection_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("inspection_result", sa.Text(), nullable=True),
        sa.Column("final_decision", sa.String(length=64), nullable=True),
        sa.Column("investor", sa.String(length=255), nullable=True),
        sa.Column("deposit_status", sa.String(length=64), nullable=True),
        sa.Column("application_status", sa.String(length=64), nullable=True),
        sa.Column("max_purchase_price", sa.Numeric(14, 2), nullable=True),
        sa.Column("market_value", sa.Numeric(14, 2), nullable=True),
        sa.Column("platform_fee", sa.Numeric(14, 2), nullable=True),
        sa.Column("delivery_cost", sa.Numeric(14, 2), nullable=True),
        sa.Column("dismantling_cost", sa.Numeric(14, 2), nullable=True),
        sa.Column("repair_cost", sa.Numeric(14, 2), nullable=True),
        sa.Column("storage_cost", sa.Numeric(14, 2), nullable=True),
        sa.Column("legal_cost", sa.Numeric(14, 2), nullable=True),
        sa.Column("other_costs", sa.Numeric(14, 2), nullable=True),
        sa.Column("analogs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["lot_record_id"], ["auction_lot_records.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lot_record_id"),
    )
    op.create_index(
        op.f("ix_auction_lot_work_items_lot_record_id"),
        "auction_lot_work_items",
        ["lot_record_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_auction_lot_work_items_lot_record_id"), table_name="auction_lot_work_items")
    op.drop_table("auction_lot_work_items")
    op.drop_index(op.f("ix_auction_lot_detail_caches_lot_record_id"), table_name="auction_lot_detail_caches")
    op.drop_table("auction_lot_detail_caches")
