"""add lot enrichment claim fields

Revision ID: 202605070004
Revises: 202605070003
Create Date: 2026-05-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202605070004"
down_revision: Union[str, None] = "202605070003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "auction_lot_records",
        sa.Column("enrichment_claimed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "auction_lot_records",
        sa.Column("enrichment_claimed_by", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "auction_lot_records",
        sa.Column("enrichment_claim_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f("ix_auction_lot_records_enrichment_claimed_at"),
        "auction_lot_records",
        ["enrichment_claimed_at"],
    )
    op.create_index(
        op.f("ix_auction_lot_records_enrichment_claimed_by"),
        "auction_lot_records",
        ["enrichment_claimed_by"],
    )
    op.create_index(
        op.f("ix_auction_lot_records_enrichment_claim_expires_at"),
        "auction_lot_records",
        ["enrichment_claim_expires_at"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_auction_lot_records_enrichment_claim_expires_at"), table_name="auction_lot_records")
    op.drop_index(op.f("ix_auction_lot_records_enrichment_claimed_by"), table_name="auction_lot_records")
    op.drop_index(op.f("ix_auction_lot_records_enrichment_claimed_at"), table_name="auction_lot_records")
    op.drop_column("auction_lot_records", "enrichment_claim_expires_at")
    op.drop_column("auction_lot_records", "enrichment_claimed_by")
    op.drop_column("auction_lot_records", "enrichment_claimed_at")
