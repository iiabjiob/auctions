"""add lot enrichment requested reason

Revision ID: 202605120002
Revises: 202605120001
Create Date: 2026-05-12 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202605120002"
down_revision = "202605120001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "auction_lot_records",
        sa.Column("enrichment_requested_reason", sa.String(length=64), nullable=True),
    )
    op.create_index(
        op.f("ix_auction_lot_records_enrichment_requested_reason"),
        "auction_lot_records",
        ["enrichment_requested_reason"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_auction_lot_records_enrichment_requested_reason"), table_name="auction_lot_records")
    op.drop_column("auction_lot_records", "enrichment_requested_reason")
