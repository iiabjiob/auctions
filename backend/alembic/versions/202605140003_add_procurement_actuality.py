"""add procurement actuality

Revision ID: 202605140003
Revises: 202605140002
Create Date: 2026-05-14 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202605140003"
down_revision = "202605140002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "procurement_lot_records",
        sa.Column("lifecycle_status", sa.String(length=32), server_default=sa.text("'active'"), nullable=False),
    )
    op.add_column("procurement_lot_records", sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("procurement_lot_records", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("procurement_lot_records", sa.Column("archive_reason", sa.Text(), nullable=True))
    op.add_column("procurement_lot_records", sa.Column("actuality_checked_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_procurement_lot_records_lifecycle_status"), "procurement_lot_records", ["lifecycle_status"])
    op.create_index(op.f("ix_procurement_lot_records_finished_at"), "procurement_lot_records", ["finished_at"])
    op.create_index(op.f("ix_procurement_lot_records_archived_at"), "procurement_lot_records", ["archived_at"])
    op.create_index(op.f("ix_procurement_lot_records_actuality_checked_at"), "procurement_lot_records", ["actuality_checked_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_procurement_lot_records_actuality_checked_at"), table_name="procurement_lot_records")
    op.drop_index(op.f("ix_procurement_lot_records_archived_at"), table_name="procurement_lot_records")
    op.drop_index(op.f("ix_procurement_lot_records_finished_at"), table_name="procurement_lot_records")
    op.drop_index(op.f("ix_procurement_lot_records_lifecycle_status"), table_name="procurement_lot_records")
    op.drop_column("procurement_lot_records", "actuality_checked_at")
    op.drop_column("procurement_lot_records", "archive_reason")
    op.drop_column("procurement_lot_records", "archived_at")
    op.drop_column("procurement_lot_records", "finished_at")
    op.drop_column("procurement_lot_records", "lifecycle_status")
