"""add lot ai analysis

Revision ID: 202604280008
Revises: 202604280007
Create Date: 2026-04-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "202604280008"
down_revision: Union[str, None] = "202604280007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "auction_lot_ai_analyses",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("lot_record_id", sa.Integer(), nullable=False),
        sa.Column("deterministic_scoring_version", sa.String(length=64), nullable=False),
        sa.Column("deterministic_score", sa.Integer(), nullable=False),
        sa.Column("deterministic_rank", sa.Integer(), nullable=True),
        sa.Column("ai_score", sa.Integer(), nullable=True),
        sa.Column("ai_rank", sa.Integer(), nullable=True),
        sa.Column("model_version", sa.String(length=128), nullable=False),
        sa.Column("prompt_version", sa.String(length=128), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column(
            "input_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "output_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("operator_feedback_status", sa.String(length=32), nullable=True),
        sa.Column("operator_feedback_comment", sa.Text(), nullable=True),
        sa.Column("operator_feedback_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("operator_feedback_by", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["lot_record_id"], ["auction_lot_records.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_auction_lot_ai_analyses_lot_record_id"), "auction_lot_ai_analyses", ["lot_record_id"])
    op.create_index(
        op.f("ix_auction_lot_ai_analyses_deterministic_scoring_version"),
        "auction_lot_ai_analyses",
        ["deterministic_scoring_version"],
    )
    op.create_index(
        op.f("ix_auction_lot_ai_analyses_deterministic_score"),
        "auction_lot_ai_analyses",
        ["deterministic_score"],
    )
    op.create_index(op.f("ix_auction_lot_ai_analyses_ai_score"), "auction_lot_ai_analyses", ["ai_score"])
    op.create_index(
        op.f("ix_auction_lot_ai_analyses_operator_feedback_status"),
        "auction_lot_ai_analyses",
        ["operator_feedback_status"],
    )
    op.create_index(op.f("ix_auction_lot_ai_analyses_created_at"), "auction_lot_ai_analyses", ["created_at"])
    op.alter_column("auction_lot_ai_analyses", "input_payload", server_default=None)
    op.alter_column("auction_lot_ai_analyses", "output_payload", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_auction_lot_ai_analyses_created_at"), table_name="auction_lot_ai_analyses")
    op.drop_index(op.f("ix_auction_lot_ai_analyses_operator_feedback_status"), table_name="auction_lot_ai_analyses")
    op.drop_index(op.f("ix_auction_lot_ai_analyses_ai_score"), table_name="auction_lot_ai_analyses")
    op.drop_index(op.f("ix_auction_lot_ai_analyses_deterministic_score"), table_name="auction_lot_ai_analyses")
    op.drop_index(
        op.f("ix_auction_lot_ai_analyses_deterministic_scoring_version"),
        table_name="auction_lot_ai_analyses",
    )
    op.drop_index(op.f("ix_auction_lot_ai_analyses_lot_record_id"), table_name="auction_lot_ai_analyses")
    op.drop_table("auction_lot_ai_analyses")
