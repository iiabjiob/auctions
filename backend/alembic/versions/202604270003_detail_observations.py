"""detail observations

Revision ID: 202604270003
Revises: 202604270002
Create Date: 2026-04-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "202604270003"
down_revision: Union[str, None] = "202604270002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "auction_lot_detail_observations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("lot_record_id", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("lot_detail", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("auction_detail", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("documents", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["lot_record_id"], ["auction_lot_records.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_auction_lot_detail_observations_content_hash"),
        "auction_lot_detail_observations",
        ["content_hash"],
    )
    op.create_index(
        op.f("ix_auction_lot_detail_observations_lot_record_id"),
        "auction_lot_detail_observations",
        ["lot_record_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_auction_lot_detail_observations_lot_record_id"),
        table_name="auction_lot_detail_observations",
    )
    op.drop_index(
        op.f("ix_auction_lot_detail_observations_content_hash"),
        table_name="auction_lot_detail_observations",
    )
    op.drop_table("auction_lot_detail_observations")
