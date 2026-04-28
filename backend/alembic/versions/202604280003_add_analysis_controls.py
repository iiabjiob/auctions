"""add analysis controls

Revision ID: 202604280003
Revises: 202604280002
Create Date: 2026-04-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202604280003"
down_revision: Union[str, None] = "202604280002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "auction_lot_work_items",
        sa.Column("exclude_from_analysis", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("auction_lot_work_items", sa.Column("exclusion_reason", sa.Text(), nullable=True))
    op.add_column("auction_lot_work_items", sa.Column("category_override", sa.String(length=255), nullable=True))
    op.add_column("auction_lot_work_items", sa.Column("target_profit", sa.Numeric(14, 2), nullable=True))
    op.alter_column("auction_lot_work_items", "exclude_from_analysis", server_default=None)


def downgrade() -> None:
    op.drop_column("auction_lot_work_items", "target_profit")
    op.drop_column("auction_lot_work_items", "category_override")
    op.drop_column("auction_lot_work_items", "exclusion_reason")
    op.drop_column("auction_lot_work_items", "exclude_from_analysis")