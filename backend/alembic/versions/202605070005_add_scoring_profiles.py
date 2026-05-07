"""add scoring profiles

Revision ID: 202605070005
Revises: 202605070004
Create Date: 2026-05-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "202605070005"
down_revision: Union[str, None] = "202605070004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scoring_profiles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("profile_identifier", sa.String(length=128), nullable=False),
        sa.Column("profile_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("profile_hash", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("profile_identifier", name="uq_scoring_profiles_identifier"),
        sa.UniqueConstraint("profile_hash", name="uq_scoring_profiles_hash"),
    )
    op.create_index("ix_scoring_profiles_name", "scoring_profiles", ["name"])
    op.create_index("ix_scoring_profiles_profile_identifier", "scoring_profiles", ["profile_identifier"])
    op.create_index("ix_scoring_profiles_profile_hash", "scoring_profiles", ["profile_hash"])
    op.create_index("ix_scoring_profiles_is_active", "scoring_profiles", ["is_active"])
    op.create_index("ix_scoring_profiles_active_updated_at", "scoring_profiles", ["is_active", "updated_at"])


def downgrade() -> None:
    op.drop_index("ix_scoring_profiles_active_updated_at", table_name="scoring_profiles")
    op.drop_index("ix_scoring_profiles_is_active", table_name="scoring_profiles")
    op.drop_index("ix_scoring_profiles_profile_hash", table_name="scoring_profiles")
    op.drop_index("ix_scoring_profiles_profile_identifier", table_name="scoring_profiles")
    op.drop_index("ix_scoring_profiles_name", table_name="scoring_profiles")
    op.drop_table("scoring_profiles")
