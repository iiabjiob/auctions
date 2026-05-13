"""add user telegram bindings

Revision ID: 202605130004
Revises: 202605130003
Create Date: 2026-05-13

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202605130004"
down_revision: Union[str, None] = "202605130003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_telegram_bindings",
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("telegram_chat_id", sa.String(length=128), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("connected_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index(
        op.f("ix_user_telegram_bindings_telegram_chat_id"),
        "user_telegram_bindings",
        ["telegram_chat_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_user_telegram_bindings_telegram_chat_id"), table_name="user_telegram_bindings")
    op.drop_table("user_telegram_bindings")
