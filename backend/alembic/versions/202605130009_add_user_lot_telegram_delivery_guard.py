"""add user lot telegram delivery guard

Revision ID: 202605130009
Revises: 202605130008
Create Date: 2026-05-13 00:00:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "202605130009"
down_revision = "202605130008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                row_number() OVER (
                    PARTITION BY user_id, lot_record_id
                    ORDER BY
                        CASE WHEN status = 'sent' THEN 0 ELSE 1 END,
                        sent_at DESC NULLS LAST,
                        scheduled_at ASC,
                        id ASC
                ) AS duplicate_rank
            FROM telegram_notification_outbox
            WHERE user_id IS NOT NULL AND status IN ('pending', 'sent')
        )
        UPDATE telegram_notification_outbox
        SET
            status = 'skipped',
            last_error = COALESCE(last_error, 'duplicate user-lot telegram delivery suppressed before unique index'),
            updated_at = now()
        WHERE id IN (
            SELECT id
            FROM ranked
            WHERE duplicate_rank > 1
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_telegram_notification_outbox_user_lot_delivery
        ON telegram_notification_outbox (user_id, lot_record_id)
        WHERE user_id IS NOT NULL AND status IN ('pending', 'sent')
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_telegram_notification_outbox_user_lot_delivery")
