"""add lot decision reports

Revision ID: 202605080001
Revises: 202605070005
Create Date: 2026-05-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "202605080001"
down_revision: Union[str, None] = "202605070005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "auction_lot_decision_reports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("lot_record_id", sa.Integer(), nullable=False),
        sa.Column("profile_hash", sa.String(length=64), nullable=True),
        sa.Column("report_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("decision_level", sa.String(length=32), nullable=False),
        sa.Column("recommendation", sa.String(length=64), nullable=False),
        sa.Column("notification_should_send", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("report_hash", sa.String(length=64), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["lot_record_id"], ["auction_lot_records.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lot_decision_reports_lot_record_id", "auction_lot_decision_reports", ["lot_record_id"])
    op.create_index("ix_lot_decision_reports_profile_hash", "auction_lot_decision_reports", ["profile_hash"])
    op.create_index("ix_lot_decision_reports_decision_level", "auction_lot_decision_reports", ["decision_level"])
    op.create_index("ix_lot_decision_reports_recommendation", "auction_lot_decision_reports", ["recommendation"])
    op.create_index(
        "ix_lot_decision_reports_notification_should_send",
        "auction_lot_decision_reports",
        ["notification_should_send"],
    )
    op.create_index("ix_lot_decision_reports_report_hash", "auction_lot_decision_reports", ["report_hash"])
    op.create_index("ix_lot_decision_reports_generated_at", "auction_lot_decision_reports", ["generated_at"])
    op.create_index(
        "uq_lot_decision_reports_lot_profile",
        "auction_lot_decision_reports",
        ["lot_record_id", "profile_hash"],
        unique=True,
        postgresql_where=sa.text("profile_hash IS NOT NULL"),
    )
    op.create_index(
        "uq_lot_decision_reports_lot_no_profile",
        "auction_lot_decision_reports",
        ["lot_record_id"],
        unique=True,
        postgresql_where=sa.text("profile_hash IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_lot_decision_reports_lot_no_profile", table_name="auction_lot_decision_reports")
    op.drop_index("uq_lot_decision_reports_lot_profile", table_name="auction_lot_decision_reports")
    op.drop_index("ix_lot_decision_reports_generated_at", table_name="auction_lot_decision_reports")
    op.drop_index("ix_lot_decision_reports_report_hash", table_name="auction_lot_decision_reports")
    op.drop_index("ix_lot_decision_reports_notification_should_send", table_name="auction_lot_decision_reports")
    op.drop_index("ix_lot_decision_reports_recommendation", table_name="auction_lot_decision_reports")
    op.drop_index("ix_lot_decision_reports_decision_level", table_name="auction_lot_decision_reports")
    op.drop_index("ix_lot_decision_reports_profile_hash", table_name="auction_lot_decision_reports")
    op.drop_index("ix_lot_decision_reports_lot_record_id", table_name="auction_lot_decision_reports")
    op.drop_table("auction_lot_decision_reports")
