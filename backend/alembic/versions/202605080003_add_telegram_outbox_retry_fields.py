"""add telegram outbox retry fields

Revision ID: 202605080003
Revises: 202605080002
Create Date: 2026-05-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202605080003"
down_revision: Union[str, None] = "202605080002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "telegram_notification_outbox",
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column("telegram_notification_outbox", sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("telegram_notification_outbox", sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("telegram_notification_outbox", sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("telegram_notification_outbox", sa.Column("last_error", sa.Text(), nullable=True))
    op.create_index("ix_telegram_notification_outbox_next_attempt_at", "telegram_notification_outbox", ["next_attempt_at"])
    op.create_index("ix_telegram_notification_outbox_sent_at", "telegram_notification_outbox", ["sent_at"])
    op.create_index("ix_telegram_notification_outbox_failed_at", "telegram_notification_outbox", ["failed_at"])


def downgrade() -> None:
    op.drop_index("ix_telegram_notification_outbox_failed_at", table_name="telegram_notification_outbox")
    op.drop_index("ix_telegram_notification_outbox_sent_at", table_name="telegram_notification_outbox")
    op.drop_index("ix_telegram_notification_outbox_next_attempt_at", table_name="telegram_notification_outbox")
    op.drop_column("telegram_notification_outbox", "last_error")
    op.drop_column("telegram_notification_outbox", "failed_at")
    op.drop_column("telegram_notification_outbox", "sent_at")
    op.drop_column("telegram_notification_outbox", "next_attempt_at")
    op.drop_column("telegram_notification_outbox", "attempt_count")
