"""add user interest profiles

Revision ID: 202605130001
Revises: 202605120005
Create Date: 2026-05-13

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "202605130001"
down_revision: Union[str, None] = "202605120005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_interest_profiles",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("owner_user_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("profile_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("min_rating", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("notification_priority_threshold", sa.String(length=32), server_default=sa.text("'medium'"), nullable=True),
        sa.Column("telegram_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_user_id", "name", name="uq_user_interest_profiles_owner_name"),
    )
    op.create_index(
        op.f("ix_user_interest_profiles_owner_user_id"),
        "user_interest_profiles",
        ["owner_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_interest_profiles_is_active"),
        "user_interest_profiles",
        ["is_active"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_user_interest_profiles_is_active"), table_name="user_interest_profiles")
    op.drop_index(op.f("ix_user_interest_profiles_owner_user_id"), table_name="user_interest_profiles")
    op.drop_table("user_interest_profiles")
