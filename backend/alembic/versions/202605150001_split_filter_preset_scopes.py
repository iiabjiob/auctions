"""split filter preset scopes

Revision ID: 202605150002
Revises: 202605150001
Create Date: 2026-05-15

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202605150002"
down_revision: Union[str, None] = "202605150001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "filter_presets",
        sa.Column("scope", sa.String(length=32), server_default=sa.text("'auction'"), nullable=True),
    )
    op.execute("UPDATE filter_presets SET scope = 'auction' WHERE scope IS NULL")
    op.alter_column("filter_presets", "scope", nullable=False)
    op.drop_constraint("uq_filter_presets_owner_name", "filter_presets", type_="unique")
    op.create_unique_constraint(
        "uq_filter_presets_owner_scope_name",
        "filter_presets",
        ["owner_user_id", "scope", "name"],
    )
    op.create_index(op.f("ix_filter_presets_scope"), "filter_presets", ["scope"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_filter_presets_scope"), table_name="filter_presets")
    op.drop_constraint("uq_filter_presets_owner_scope_name", "filter_presets", type_="unique")
    op.create_unique_constraint("uq_filter_presets_owner_name", "filter_presets", ["owner_user_id", "name"])
    op.drop_column("filter_presets", "scope")
