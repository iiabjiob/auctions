"""add telegram notification outbox

Revision ID: 202605080002
Revises: 202605080001
Create Date: 2026-05-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "202605080002"
down_revision: Union[str, None] = "202605080001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "telegram_notification_outbox",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("lot_record_id", sa.Integer(), nullable=False),
        sa.Column("decision_report_id", sa.Integer(), nullable=False),
        sa.Column("dedupe_key", sa.String(length=128), nullable=False),
        sa.Column("cooldown_key", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("priority", sa.String(length=32), nullable=False),
        sa.Column("message_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("report_hash", sa.String(length=64), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'sent', 'failed', 'skipped')",
            name="ck_telegram_notification_outbox_status",
        ),
        sa.ForeignKeyConstraint(["decision_report_id"], ["auction_lot_decision_reports.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lot_record_id"], ["auction_lot_records.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key", name="uq_telegram_notification_outbox_dedupe_key"),
    )
    op.create_index("ix_telegram_notification_outbox_lot_record_id", "telegram_notification_outbox", ["lot_record_id"])
    op.create_index(
        "ix_telegram_notification_outbox_decision_report_id",
        "telegram_notification_outbox",
        ["decision_report_id"],
    )
    op.create_index("ix_telegram_notification_outbox_cooldown_key", "telegram_notification_outbox", ["cooldown_key"])
    op.create_index("ix_telegram_notification_outbox_status", "telegram_notification_outbox", ["status"])
    op.create_index("ix_telegram_notification_outbox_priority", "telegram_notification_outbox", ["priority"])
    op.create_index("ix_telegram_notification_outbox_report_hash", "telegram_notification_outbox", ["report_hash"])
    op.create_index("ix_telegram_notification_outbox_cooldown_until", "telegram_notification_outbox", ["cooldown_until"])


def downgrade() -> None:
    op.drop_index("ix_telegram_notification_outbox_cooldown_until", table_name="telegram_notification_outbox")
    op.drop_index("ix_telegram_notification_outbox_report_hash", table_name="telegram_notification_outbox")
    op.drop_index("ix_telegram_notification_outbox_priority", table_name="telegram_notification_outbox")
    op.drop_index("ix_telegram_notification_outbox_status", table_name="telegram_notification_outbox")
    op.drop_index("ix_telegram_notification_outbox_cooldown_key", table_name="telegram_notification_outbox")
    op.drop_index("ix_telegram_notification_outbox_decision_report_id", table_name="telegram_notification_outbox")
    op.drop_index("ix_telegram_notification_outbox_lot_record_id", table_name="telegram_notification_outbox")
    op.drop_table("telegram_notification_outbox")
