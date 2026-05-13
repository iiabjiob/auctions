"""add telegram connect tokens

Revision ID: 202605130006
Revises: 202605130005
Create Date: 2026-05-13

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202605130006"
down_revision: Union[str, None] = "202605130005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "telegram_connect_tokens",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_telegram_connect_tokens_token_hash"),
    )
    op.create_index(op.f("ix_telegram_connect_tokens_user_id"), "telegram_connect_tokens", ["user_id"])
    op.create_index(op.f("ix_telegram_connect_tokens_expires_at"), "telegram_connect_tokens", ["expires_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_telegram_connect_tokens_expires_at"), table_name="telegram_connect_tokens")
    op.drop_index(op.f("ix_telegram_connect_tokens_user_id"), table_name="telegram_connect_tokens")
    op.drop_table("telegram_connect_tokens")
