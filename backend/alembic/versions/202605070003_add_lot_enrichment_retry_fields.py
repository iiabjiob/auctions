"""add lot enrichment retry fields

Revision ID: 202605070003
Revises: 202605070002
Create Date: 2026-05-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202605070003"
down_revision: Union[str, None] = "202605070002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "auction_lot_records",
        sa.Column("last_enrichment_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "auction_lot_records",
        sa.Column("enrichment_attempt_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "auction_lot_records",
        sa.Column("next_enrichment_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("auction_lot_records", sa.Column("last_enrichment_error", sa.Text(), nullable=True))
    op.create_index(
        op.f("ix_auction_lot_records_last_enrichment_attempt_at"),
        "auction_lot_records",
        ["last_enrichment_attempt_at"],
    )
    op.create_index(
        op.f("ix_auction_lot_records_next_enrichment_attempt_at"),
        "auction_lot_records",
        ["next_enrichment_attempt_at"],
    )
    op.alter_column("auction_lot_records", "enrichment_attempt_count", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_auction_lot_records_next_enrichment_attempt_at"), table_name="auction_lot_records")
    op.drop_index(op.f("ix_auction_lot_records_last_enrichment_attempt_at"), table_name="auction_lot_records")
    op.drop_column("auction_lot_records", "last_enrichment_error")
    op.drop_column("auction_lot_records", "next_enrichment_attempt_at")
    op.drop_column("auction_lot_records", "enrichment_attempt_count")
    op.drop_column("auction_lot_records", "last_enrichment_attempt_at")
