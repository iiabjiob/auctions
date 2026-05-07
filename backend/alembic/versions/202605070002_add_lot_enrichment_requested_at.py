"""add lot enrichment requested marker

Revision ID: 202605070002
Revises: 202605070001
Create Date: 2026-05-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202605070002"
down_revision: Union[str, None] = "202605070001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "auction_lot_records",
        sa.Column("enrichment_requested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f("ix_auction_lot_records_enrichment_requested_at"),
        "auction_lot_records",
        ["enrichment_requested_at"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_auction_lot_records_enrichment_requested_at"), table_name="auction_lot_records")
    op.drop_column("auction_lot_records", "enrichment_requested_at")
