"""expand procurement v1 fields

Revision ID: 202605130011
Revises: 202605130010
Create Date: 2026-05-13 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "202605130011"
down_revision = "202605130010"
branch_labels = None
depends_on = None


TABLE = "procurement_lot_records"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("customer_inn", sa.String(length=32), nullable=True))
    op.add_column(TABLE, sa.Column("delivery_region", sa.String(length=255), nullable=True))
    op.add_column(TABLE, sa.Column("delivery_address", sa.Text(), nullable=True))
    op.add_column(TABLE, sa.Column("specification_url", sa.Text(), nullable=True))
    op.add_column(TABLE, sa.Column("documents_url", sa.Text(), nullable=True))
    op.add_column(TABLE, sa.Column("certificate_requirements", sa.Text(), nullable=True))
    op.add_column(TABLE, sa.Column("documentation_present", sa.Boolean(), nullable=True))
    op.add_column(TABLE, sa.Column("category", sa.String(length=64), nullable=True))
    op.add_column(
        TABLE,
        sa.Column(
            "matched_keywords",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        TABLE,
        sa.Column(
            "excluded_keywords",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(TABLE, sa.Column("filter_reason", sa.Text(), nullable=True))
    op.add_column(
        TABLE,
        sa.Column("workflow_status", sa.String(length=64), server_default=sa.text("'new'"), nullable=False),
    )
    op.add_column(TABLE, sa.Column("assignee", sa.String(length=255), nullable=True))
    op.add_column(TABLE, sa.Column("comment", sa.Text(), nullable=True))
    op.add_column(TABLE, sa.Column("final_decision", sa.String(length=64), nullable=True))
    op.add_column(TABLE, sa.Column("rejection_reason", sa.Text(), nullable=True))
    op.add_column(TABLE, sa.Column("bid_security_amount", sa.Numeric(18, 2), nullable=True))
    op.add_column(TABLE, sa.Column("contract_security_amount", sa.Numeric(18, 2), nullable=True))
    op.add_column(TABLE, sa.Column("prepayment_percent", sa.Numeric(5, 2), nullable=True))
    op.add_column(TABLE, sa.Column("payment_terms", sa.Text(), nullable=True))
    op.add_column(TABLE, sa.Column("quantity", sa.Numeric(18, 3), nullable=True))
    op.add_column(TABLE, sa.Column("unit_nmck", sa.Numeric(18, 2), nullable=True))
    op.add_column(TABLE, sa.Column("cost_realistic", sa.Numeric(18, 2), nullable=True))
    op.add_column(TABLE, sa.Column("cost_cautious", sa.Numeric(18, 2), nullable=True))
    op.add_column(TABLE, sa.Column("net_profit", sa.Numeric(18, 2), nullable=True))
    op.add_column(TABLE, sa.Column("profitability", sa.Numeric(10, 6), nullable=True))
    op.add_column(TABLE, sa.Column("roi", sa.Numeric(10, 6), nullable=True))
    op.add_column(TABLE, sa.Column("cash_gap_peak", sa.Numeric(18, 2), nullable=True))

    for column in (
        "assignee",
        "category",
        "customer_inn",
        "delivery_region",
        "documentation_present",
        "final_decision",
        "net_profit",
        "profitability",
        "roi",
        "workflow_status",
    ):
        op.create_index(op.f(f"ix_{TABLE}_{column}"), TABLE, [column])


def downgrade() -> None:
    for column in (
        "workflow_status",
        "roi",
        "profitability",
        "net_profit",
        "final_decision",
        "documentation_present",
        "delivery_region",
        "customer_inn",
        "category",
        "assignee",
    ):
        op.drop_index(op.f(f"ix_{TABLE}_{column}"), table_name=TABLE)

    for column in (
        "cash_gap_peak",
        "roi",
        "profitability",
        "net_profit",
        "cost_cautious",
        "cost_realistic",
        "unit_nmck",
        "quantity",
        "payment_terms",
        "prepayment_percent",
        "contract_security_amount",
        "bid_security_amount",
        "rejection_reason",
        "final_decision",
        "comment",
        "assignee",
        "workflow_status",
        "filter_reason",
        "excluded_keywords",
        "matched_keywords",
        "category",
        "documentation_present",
        "certificate_requirements",
        "documents_url",
        "specification_url",
        "delivery_address",
        "delivery_region",
        "customer_inn",
    ):
        op.drop_column(TABLE, column)
