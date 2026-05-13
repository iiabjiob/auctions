"""add procurement telegram outbox

Revision ID: 202605130014
Revises: 202605130013
Create Date: 2026-05-13 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "202605130014"
down_revision = "202605130013"
branch_labels = None
depends_on = None


TABLE = "procurement_telegram_notification_outbox"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("procurement_lot_record_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=32), nullable=True),
        sa.Column("telegram_chat_id", sa.String(length=128), nullable=True),
        sa.Column("dedupe_key", sa.String(length=255), nullable=False),
        sa.Column("cooldown_key", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("priority", sa.String(length=32), nullable=False),
        sa.Column("message_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("event_hash", sa.String(length=64), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'sent', 'failed', 'skipped')",
            name="ck_procurement_telegram_outbox_status",
        ),
        sa.ForeignKeyConstraint(["procurement_lot_record_id"], ["procurement_lot_records.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key", name="uq_procurement_telegram_outbox_dedupe_key"),
    )
    for column in (
        "procurement_lot_record_id",
        "event_type",
        "user_id",
        "cooldown_key",
        "status",
        "priority",
        "event_hash",
        "cooldown_until",
        "next_attempt_at",
        "sent_at",
        "failed_at",
    ):
        op.create_index(op.f(f"ix_{TABLE}_{column}"), TABLE, [column])
    op.execute(
        """
        CREATE UNIQUE INDEX uq_procurement_telegram_outbox_lot_event_delivery
        ON procurement_telegram_notification_outbox (procurement_lot_record_id, event_type)
        WHERE status IN ('pending', 'sent')
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_procurement_telegram_outbox_lot_event_delivery")
    for column in (
        "failed_at",
        "sent_at",
        "next_attempt_at",
        "cooldown_until",
        "event_hash",
        "priority",
        "status",
        "cooldown_key",
        "user_id",
        "event_type",
        "procurement_lot_record_id",
    ):
        op.drop_index(op.f(f"ix_{TABLE}_{column}"), table_name=TABLE)
    op.drop_table(TABLE)
