"""add source http exchange diagnostics

Revision ID: 202605130007
Revises: 202605130006
Create Date: 2026-05-13 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202605130007"
down_revision = "202605130006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auction_source_http_exchanges",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source_code", sa.String(length=64), sa.ForeignKey("auction_source_states.code"), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("host", sa.String(length=255), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("request_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("response_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_type", sa.String(length=128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(op.f("ix_auction_source_http_exchanges_source_code"), "auction_source_http_exchanges", ["source_code"])
    op.create_index(op.f("ix_auction_source_http_exchanges_operation"), "auction_source_http_exchanges", ["operation"])
    op.create_index(op.f("ix_auction_source_http_exchanges_host"), "auction_source_http_exchanges", ["host"])
    op.create_index(op.f("ix_auction_source_http_exchanges_started_at"), "auction_source_http_exchanges", ["started_at"])
    op.create_index(op.f("ix_auction_source_http_exchanges_completed_at"), "auction_source_http_exchanges", ["completed_at"])
    op.create_index(op.f("ix_auction_source_http_exchanges_status_code"), "auction_source_http_exchanges", ["status_code"])
    op.create_index(op.f("ix_auction_source_http_exchanges_ok"), "auction_source_http_exchanges", ["ok"])
    op.create_index(op.f("ix_auction_source_http_exchanges_error_type"), "auction_source_http_exchanges", ["error_type"])


def downgrade() -> None:
    op.drop_index(op.f("ix_auction_source_http_exchanges_error_type"), table_name="auction_source_http_exchanges")
    op.drop_index(op.f("ix_auction_source_http_exchanges_ok"), table_name="auction_source_http_exchanges")
    op.drop_index(op.f("ix_auction_source_http_exchanges_status_code"), table_name="auction_source_http_exchanges")
    op.drop_index(op.f("ix_auction_source_http_exchanges_completed_at"), table_name="auction_source_http_exchanges")
    op.drop_index(op.f("ix_auction_source_http_exchanges_started_at"), table_name="auction_source_http_exchanges")
    op.drop_index(op.f("ix_auction_source_http_exchanges_host"), table_name="auction_source_http_exchanges")
    op.drop_index(op.f("ix_auction_source_http_exchanges_operation"), table_name="auction_source_http_exchanges")
    op.drop_index(op.f("ix_auction_source_http_exchanges_source_code"), table_name="auction_source_http_exchanges")
    op.drop_table("auction_source_http_exchanges")
