"""add lot search text

Revision ID: 202605090001
Revises: 202605080003
Create Date: 2026-05-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202605090001"
down_revision: Union[str, None] = "202605080003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("auction_lot_records", sa.Column("search_text", sa.Text(), nullable=True))
    op.execute(
        """
        UPDATE auction_lot_records
        SET search_text = lower(
            btrim(
                regexp_replace(
                    concat_ws(
                        ' ',
                        lot_name,
                        datagrid_row ->> 'source_title',
                        coalesce(datagrid_row ->> 'location_region', normalized_item #>> '{lot,region}'),
                        coalesce(datagrid_row ->> 'category', datagrid_row ->> 'model_category', normalized_item #>> '{lot,category}'),
                        coalesce(datagrid_row ->> 'organizer_name', normalized_item #>> '{organizer,name}'),
                        coalesce(datagrid_row ->> 'debtor_name', normalized_item #>> '{debtor,name}'),
                        coalesce(datagrid_row ->> 'location', normalized_item #>> '{lot,location}')
                    ),
                    '\\s+',
                    ' ',
                    'g'
                )
            )
        )
        """
    )


def downgrade() -> None:
    op.drop_column("auction_lot_records", "search_text")
