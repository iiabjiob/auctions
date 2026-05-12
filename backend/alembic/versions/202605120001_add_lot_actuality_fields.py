"""add lot actuality fields

Revision ID: 202605120001
Revises: 202605110001
Create Date: 2026-05-12 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202605120001"
down_revision = "202605110001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("auction_lot_records", sa.Column("publication_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("auction_lot_records", sa.Column("application_start_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "auction_lot_records",
        sa.Column("application_deadline_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("auction_lot_records", sa.Column("auction_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("auction_lot_records", sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "auction_lot_records",
        sa.Column(
            "lifecycle_status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
    )
    op.add_column("auction_lot_records", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("auction_lot_records", sa.Column("archive_reason", sa.Text(), nullable=True))
    op.add_column(
        "auction_lot_records",
        sa.Column("actuality_checked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(op.f("ix_auction_lot_records_publication_at"), "auction_lot_records", ["publication_at"])
    op.create_index(
        op.f("ix_auction_lot_records_application_start_at"),
        "auction_lot_records",
        ["application_start_at"],
    )
    op.create_index(
        op.f("ix_auction_lot_records_application_deadline_at"),
        "auction_lot_records",
        ["application_deadline_at"],
    )
    op.create_index(op.f("ix_auction_lot_records_auction_at"), "auction_lot_records", ["auction_at"])
    op.create_index(op.f("ix_auction_lot_records_finished_at"), "auction_lot_records", ["finished_at"])
    op.create_index(op.f("ix_auction_lot_records_lifecycle_status"), "auction_lot_records", ["lifecycle_status"])
    op.create_index(op.f("ix_auction_lot_records_archived_at"), "auction_lot_records", ["archived_at"])
    op.create_index(op.f("ix_auction_lot_records_actuality_checked_at"), "auction_lot_records", ["actuality_checked_at"])
    op.create_index(
        op.f("ix_auction_lot_records_lifecycle_status_rating_score"),
        "auction_lot_records",
        ["lifecycle_status", "rating_score"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_auction_lot_records_lifecycle_status_rating_score"), table_name="auction_lot_records")
    op.drop_index(op.f("ix_auction_lot_records_actuality_checked_at"), table_name="auction_lot_records")
    op.drop_index(op.f("ix_auction_lot_records_archived_at"), table_name="auction_lot_records")
    op.drop_index(op.f("ix_auction_lot_records_lifecycle_status"), table_name="auction_lot_records")
    op.drop_index(op.f("ix_auction_lot_records_finished_at"), table_name="auction_lot_records")
    op.drop_index(op.f("ix_auction_lot_records_auction_at"), table_name="auction_lot_records")
    op.drop_index(op.f("ix_auction_lot_records_application_deadline_at"), table_name="auction_lot_records")
    op.drop_index(op.f("ix_auction_lot_records_application_start_at"), table_name="auction_lot_records")
    op.drop_index(op.f("ix_auction_lot_records_publication_at"), table_name="auction_lot_records")
    op.drop_column("auction_lot_records", "actuality_checked_at")
    op.drop_column("auction_lot_records", "archive_reason")
    op.drop_column("auction_lot_records", "archived_at")
    op.drop_column("auction_lot_records", "lifecycle_status")
    op.drop_column("auction_lot_records", "finished_at")
    op.drop_column("auction_lot_records", "auction_at")
    op.drop_column("auction_lot_records", "application_deadline_at")
    op.drop_column("auction_lot_records", "application_start_at")
    op.drop_column("auction_lot_records", "publication_at")
