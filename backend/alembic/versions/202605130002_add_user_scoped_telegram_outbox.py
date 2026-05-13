"""add user scoped telegram outbox fields

Revision ID: 202605130002
Revises: 202605130001
Create Date: 2026-05-13

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202605130002"
down_revision: Union[str, None] = "202605130001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("telegram_notification_outbox", sa.Column("user_id", sa.String(length=32), nullable=True))
    op.add_column("telegram_notification_outbox", sa.Column("telegram_chat_id", sa.String(length=128), nullable=True))
    op.add_column(
        "telegram_notification_outbox",
        sa.Column("interest_profile_id", sa.String(length=32), nullable=True),
    )
    op.create_foreign_key(
        "fk_telegram_notification_outbox_user_id_users",
        "telegram_notification_outbox",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_telegram_notification_outbox_interest_profile_id_user_interest_profiles",
        "telegram_notification_outbox",
        "user_interest_profiles",
        ["interest_profile_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_telegram_notification_outbox_user_id", "telegram_notification_outbox", ["user_id"])
    op.create_index(
        "ix_telegram_notification_outbox_interest_profile_id",
        "telegram_notification_outbox",
        ["interest_profile_id"],
    )
    op.create_index(
        "ix_telegram_notification_outbox_status_user_priority",
        "telegram_notification_outbox",
        ["status", "user_id", "priority"],
    )


def downgrade() -> None:
    op.drop_index("ix_telegram_notification_outbox_status_user_priority", table_name="telegram_notification_outbox")
    op.drop_index("ix_telegram_notification_outbox_interest_profile_id", table_name="telegram_notification_outbox")
    op.drop_index("ix_telegram_notification_outbox_user_id", table_name="telegram_notification_outbox")
    op.drop_constraint(
        "fk_telegram_notification_outbox_interest_profile_id_user_interest_profiles",
        "telegram_notification_outbox",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_telegram_notification_outbox_user_id_users",
        "telegram_notification_outbox",
        type_="foreignkey",
    )
    op.drop_column("telegram_notification_outbox", "interest_profile_id")
    op.drop_column("telegram_notification_outbox", "telegram_chat_id")
    op.drop_column("telegram_notification_outbox", "user_id")
