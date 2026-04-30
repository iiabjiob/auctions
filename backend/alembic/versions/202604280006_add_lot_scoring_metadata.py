"""add lot scoring metadata

Revision ID: 202604280006
Revises: 202604280005
Create Date: 2026-04-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "202604280006"
down_revision: Union[str, None] = "202604280005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "auction_lot_records",
        sa.Column("scoring_version", sa.String(length=64), server_default="unscored", nullable=False),
    )
    op.add_column("auction_lot_records", sa.Column("scored_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("auction_lot_records", sa.Column("score_input_hash", sa.String(length=64), nullable=True))
    op.add_column(
        "auction_lot_records",
        sa.Column(
            "score_breakdown",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.create_index(op.f("ix_auction_lot_records_scoring_version"), "auction_lot_records", ["scoring_version"])
    op.create_index(op.f("ix_auction_lot_records_scored_at"), "auction_lot_records", ["scored_at"])
    op.create_index(op.f("ix_auction_lot_records_score_input_hash"), "auction_lot_records", ["score_input_hash"])
    op.alter_column("auction_lot_records", "scoring_version", server_default=None)
    op.alter_column("auction_lot_records", "score_breakdown", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_auction_lot_records_score_input_hash"), table_name="auction_lot_records")
    op.drop_index(op.f("ix_auction_lot_records_scored_at"), table_name="auction_lot_records")
    op.drop_index(op.f("ix_auction_lot_records_scoring_version"), table_name="auction_lot_records")
    op.drop_column("auction_lot_records", "score_breakdown")
    op.drop_column("auction_lot_records", "score_input_hash")
    op.drop_column("auction_lot_records", "scored_at")
    op.drop_column("auction_lot_records", "scoring_version")
