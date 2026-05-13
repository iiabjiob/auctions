"""add procurement lots

Revision ID: 202605130010
Revises: 202605130009
Create Date: 2026-05-13 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "202605130010"
down_revision = "202605130009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "procurement_source_states",
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("website", sa.String(length=512), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("code"),
    )
    op.create_index(
        op.f("ix_procurement_source_states_last_synced_at"),
        "procurement_source_states",
        ["last_synced_at"],
        unique=False,
    )

    op.create_table(
        "procurement_lot_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_code", sa.String(length=64), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=False),
        sa.Column("registry_number", sa.String(length=128), nullable=False),
        sa.Column("law", sa.String(length=32), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=255), nullable=True),
        sa.Column("customer_name", sa.Text(), nullable=True),
        sa.Column("organizer_name", sa.Text(), nullable=True),
        sa.Column("procedure_type", sa.String(length=255), nullable=True),
        sa.Column("platform_name", sa.Text(), nullable=True),
        sa.Column("region", sa.String(length=255), nullable=True),
        sa.Column("initial_price", sa.String(length=128), nullable=True),
        sa.Column("initial_price_value", sa.Numeric(18, 2), nullable=True),
        sa.Column("currency", sa.String(length=16), nullable=True),
        sa.Column("publication_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("application_deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notice_url", sa.Text(), nullable=True),
        sa.Column("print_url", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_new", sa.Boolean(), nullable=False),
        sa.Column("attractiveness_score", sa.Integer(), nullable=False),
        sa.Column("attractiveness_level", sa.String(length=32), nullable=False),
        sa.Column("attractiveness_reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("search_text", sa.Text(), nullable=True),
        sa.Column("normalized_item", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("raw_item", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["source_code"], ["procurement_source_states.code"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_code", "external_id", name="uq_procurement_lot_records_source_external_id"),
    )
    op.create_index("ix_procurement_lot_records_score_status", "procurement_lot_records", ["attractiveness_score", "status"])
    op.create_index("ix_procurement_lot_records_law_status", "procurement_lot_records", ["law", "status"])
    for column in (
        "application_deadline_at",
        "attractiveness_level",
        "attractiveness_score",
        "external_id",
        "initial_price_value",
        "is_new",
        "law",
        "publication_at",
        "registry_number",
        "region",
        "source_code",
        "status",
        "status_changed_at",
    ):
        op.create_index(op.f(f"ix_procurement_lot_records_{column}"), "procurement_lot_records", [column])


def downgrade() -> None:
    op.drop_table("procurement_lot_records")
    op.drop_table("procurement_source_states")
