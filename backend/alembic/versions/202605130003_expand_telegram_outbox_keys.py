"""expand telegram outbox keys

Revision ID: 202605130003
Revises: 202605130002
Create Date: 2026-05-13

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202605130003"
down_revision: Union[str, None] = "202605130002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "telegram_notification_outbox",
        "dedupe_key",
        existing_type=sa.String(length=128),
        type_=sa.String(length=255),
        existing_nullable=False,
    )
    op.alter_column(
        "telegram_notification_outbox",
        "cooldown_key",
        existing_type=sa.String(length=128),
        type_=sa.String(length=255),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "telegram_notification_outbox",
        "cooldown_key",
        existing_type=sa.String(length=255),
        type_=sa.String(length=128),
        existing_nullable=False,
    )
    op.alter_column(
        "telegram_notification_outbox",
        "dedupe_key",
        existing_type=sa.String(length=255),
        type_=sa.String(length=128),
        existing_nullable=False,
    )
