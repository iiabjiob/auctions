"""add owner scoring profile

Revision ID: 202604280007
Revises: 202604280006
Create Date: 2026-04-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "202604280007"
down_revision: Union[str, None] = "202604280006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "auction_analysis_configs",
        sa.Column(
            "owner_profile",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "auction_analysis_configs",
        sa.Column(
            "dimension_weights",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.alter_column("auction_analysis_configs", "owner_profile", server_default=None)
    op.alter_column("auction_analysis_configs", "dimension_weights", server_default=None)


def downgrade() -> None:
    op.drop_column("auction_analysis_configs", "dimension_weights")
    op.drop_column("auction_analysis_configs", "owner_profile")
