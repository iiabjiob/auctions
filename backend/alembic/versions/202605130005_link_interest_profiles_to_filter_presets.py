"""link interest profiles to filter presets

Revision ID: 202605130005
Revises: 202605130004
Create Date: 2026-05-13

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202605130005"
down_revision: Union[str, None] = "202605130004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_interest_profiles",
        sa.Column("source_filter_preset_id", sa.String(length=32), nullable=True),
    )
    op.create_foreign_key(
        "fk_user_interest_profiles_source_filter_preset_id",
        "user_interest_profiles",
        "filter_presets",
        ["source_filter_preset_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_user_interest_profiles_source_filter_preset_id"),
        "user_interest_profiles",
        ["source_filter_preset_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_user_interest_profiles_source_filter_preset_id"), table_name="user_interest_profiles")
    op.drop_constraint(
        "fk_user_interest_profiles_source_filter_preset_id",
        "user_interest_profiles",
        type_="foreignkey",
    )
    op.drop_column("user_interest_profiles", "source_filter_preset_id")
