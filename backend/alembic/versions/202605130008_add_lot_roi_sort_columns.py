"""add lot roi sort columns

Revision ID: 202605130008
Revises: 202605130007
Create Date: 2026-05-13 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202605130008"
down_revision = "202605130007"
branch_labels = None
depends_on = None


def _json_numeric(key: str) -> str:
    return (
        "NULLIF(NULLIF(NULLIF("
        f"replace(regexp_replace(datagrid_row->>'{key}', '[^0-9,.-]+', '', 'g'), ',', '.'), "
        "''), '-'), '.')::numeric"
    )


def upgrade() -> None:
    op.add_column("auction_lot_records", sa.Column("roi_sort_value", sa.Numeric(18, 6), nullable=True))
    op.add_column("auction_lot_records", sa.Column("market_discount_sort_value", sa.Numeric(18, 6), nullable=True))

    price = f"COALESCE({_json_numeric('current_price_value')}, {_json_numeric('initial_price_value')})"
    expenses = " + ".join(
        f"COALESCE({_json_numeric(field)}, 0)"
        for field in (
            "platform_fee",
            "delivery_cost",
            "dismantling_cost",
            "repair_cost",
            "storage_cost",
            "legal_cost",
            "other_costs",
        )
    )
    full_entry_cost = f"(({price}) + ({expenses}))"
    market_value = _json_numeric("market_value")

    op.execute(
        f"""
        UPDATE auction_lot_records
        SET
            roi_sort_value = CASE
                WHEN {market_value} IS NULL OR {price} IS NULL OR NULLIF({full_entry_cost}, 0) IS NULL THEN NULL
                ELSE ({market_value} - {full_entry_cost}) / NULLIF({full_entry_cost}, 0)
            END,
            market_discount_sort_value = CASE
                WHEN {market_value} IS NULL OR {price} IS NULL OR NULLIF({market_value}, 0) IS NULL THEN NULL
                ELSE 1 - ({price} / NULLIF({market_value}, 0))
            END
        """
    )

    op.create_index(op.f("ix_auction_lot_records_roi_sort_value"), "auction_lot_records", ["roi_sort_value"])
    op.create_index(
        op.f("ix_auction_lot_records_market_discount_sort_value"),
        "auction_lot_records",
        ["market_discount_sort_value"],
    )
    op.execute(
        """
        CREATE INDEX ix_auction_lot_records_lifecycle_roi_sort
        ON auction_lot_records (lifecycle_status, roi_sort_value DESC NULLS LAST, id)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_auction_lot_records_lifecycle_market_discount_sort
        ON auction_lot_records (lifecycle_status, market_discount_sort_value DESC NULLS LAST, id)
        """
    )


def downgrade() -> None:
    op.drop_index("ix_auction_lot_records_lifecycle_market_discount_sort", table_name="auction_lot_records")
    op.drop_index("ix_auction_lot_records_lifecycle_roi_sort", table_name="auction_lot_records")
    op.drop_index(op.f("ix_auction_lot_records_market_discount_sort_value"), table_name="auction_lot_records")
    op.drop_index(op.f("ix_auction_lot_records_roi_sort_value"), table_name="auction_lot_records")
    op.drop_column("auction_lot_records", "market_discount_sort_value")
    op.drop_column("auction_lot_records", "roi_sort_value")
