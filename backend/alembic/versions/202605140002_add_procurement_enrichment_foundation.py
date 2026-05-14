"""add procurement enrichment foundation

Revision ID: 202605140002
Revises: 202605140001
Create Date: 2026-05-14 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "202605140002"
down_revision = "202605140001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("procurement_lot_records", sa.Column("enrichment_requested_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("procurement_lot_records", sa.Column("enrichment_requested_reason", sa.String(length=64), nullable=True))
    op.add_column("procurement_lot_records", sa.Column("last_enrichment_attempt_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "procurement_lot_records",
        sa.Column("enrichment_attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column("procurement_lot_records", sa.Column("next_enrichment_attempt_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("procurement_lot_records", sa.Column("last_enrichment_error", sa.Text(), nullable=True))
    op.add_column("procurement_lot_records", sa.Column("enrichment_claimed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("procurement_lot_records", sa.Column("enrichment_claimed_by", sa.String(length=255), nullable=True))
    op.add_column("procurement_lot_records", sa.Column("enrichment_claim_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_procurement_lot_records_enrichment_requested_at"), "procurement_lot_records", ["enrichment_requested_at"])
    op.create_index(op.f("ix_procurement_lot_records_enrichment_requested_reason"), "procurement_lot_records", ["enrichment_requested_reason"])
    op.create_index(op.f("ix_procurement_lot_records_last_enrichment_attempt_at"), "procurement_lot_records", ["last_enrichment_attempt_at"])
    op.create_index(op.f("ix_procurement_lot_records_next_enrichment_attempt_at"), "procurement_lot_records", ["next_enrichment_attempt_at"])
    op.create_index(op.f("ix_procurement_lot_records_enrichment_claimed_at"), "procurement_lot_records", ["enrichment_claimed_at"])
    op.create_index(op.f("ix_procurement_lot_records_enrichment_claimed_by"), "procurement_lot_records", ["enrichment_claimed_by"])
    op.create_index(op.f("ix_procurement_lot_records_enrichment_claim_expires_at"), "procurement_lot_records", ["enrichment_claim_expires_at"])

    op.create_table(
        "procurement_lot_observations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("procurement_lot_record_id", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=255), nullable=True),
        sa.Column("normalized_item", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("raw_item", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["procurement_lot_record_id"], ["procurement_lot_records.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_procurement_lot_observations_procurement_lot_record_id"), "procurement_lot_observations", ["procurement_lot_record_id"])
    op.create_index(op.f("ix_procurement_lot_observations_content_hash"), "procurement_lot_observations", ["content_hash"])
    op.create_index(op.f("ix_procurement_lot_observations_status"), "procurement_lot_observations", ["status"])

    op.create_table(
        "procurement_lot_detail_caches",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("procurement_lot_record_id", sa.Integer(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("detail_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("documents", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["procurement_lot_record_id"], ["procurement_lot_records.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("procurement_lot_record_id"),
    )
    op.create_index(op.f("ix_procurement_lot_detail_caches_procurement_lot_record_id"), "procurement_lot_detail_caches", ["procurement_lot_record_id"])

    op.create_table(
        "procurement_lot_detail_observations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("procurement_lot_record_id", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("detail_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("documents", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["procurement_lot_record_id"], ["procurement_lot_records.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_procurement_lot_detail_observations_procurement_lot_record_id"), "procurement_lot_detail_observations", ["procurement_lot_record_id"])
    op.create_index(op.f("ix_procurement_lot_detail_observations_content_hash"), "procurement_lot_detail_observations", ["content_hash"])

    op.create_table(
        "procurement_source_http_exchanges",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_code", sa.String(length=64), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("host", sa.String(length=255), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("request_bytes", sa.Integer(), nullable=False),
        sa.Column("response_bytes", sa.Integer(), nullable=False),
        sa.Column("error_type", sa.String(length=128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["source_code"], ["procurement_source_states.code"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("source_code", "operation", "host", "started_at", "status_code", "ok", "error_type"):
        op.create_index(op.f(f"ix_procurement_source_http_exchanges_{column}"), "procurement_source_http_exchanges", [column])


def downgrade() -> None:
    for column in ("error_type", "ok", "status_code", "started_at", "host", "operation", "source_code"):
        op.drop_index(op.f(f"ix_procurement_source_http_exchanges_{column}"), table_name="procurement_source_http_exchanges")
    op.drop_table("procurement_source_http_exchanges")
    op.drop_index(op.f("ix_procurement_lot_detail_observations_content_hash"), table_name="procurement_lot_detail_observations")
    op.drop_index(op.f("ix_procurement_lot_detail_observations_procurement_lot_record_id"), table_name="procurement_lot_detail_observations")
    op.drop_table("procurement_lot_detail_observations")
    op.drop_index(op.f("ix_procurement_lot_detail_caches_procurement_lot_record_id"), table_name="procurement_lot_detail_caches")
    op.drop_table("procurement_lot_detail_caches")
    op.drop_index(op.f("ix_procurement_lot_observations_status"), table_name="procurement_lot_observations")
    op.drop_index(op.f("ix_procurement_lot_observations_content_hash"), table_name="procurement_lot_observations")
    op.drop_index(op.f("ix_procurement_lot_observations_procurement_lot_record_id"), table_name="procurement_lot_observations")
    op.drop_table("procurement_lot_observations")
    op.drop_index(op.f("ix_procurement_lot_records_enrichment_claim_expires_at"), table_name="procurement_lot_records")
    op.drop_index(op.f("ix_procurement_lot_records_enrichment_claimed_by"), table_name="procurement_lot_records")
    op.drop_index(op.f("ix_procurement_lot_records_enrichment_claimed_at"), table_name="procurement_lot_records")
    op.drop_index(op.f("ix_procurement_lot_records_next_enrichment_attempt_at"), table_name="procurement_lot_records")
    op.drop_index(op.f("ix_procurement_lot_records_last_enrichment_attempt_at"), table_name="procurement_lot_records")
    op.drop_index(op.f("ix_procurement_lot_records_enrichment_requested_reason"), table_name="procurement_lot_records")
    op.drop_index(op.f("ix_procurement_lot_records_enrichment_requested_at"), table_name="procurement_lot_records")
    for column in (
        "enrichment_claim_expires_at",
        "enrichment_claimed_by",
        "enrichment_claimed_at",
        "last_enrichment_error",
        "next_enrichment_attempt_at",
        "enrichment_attempt_count",
        "last_enrichment_attempt_at",
        "enrichment_requested_reason",
        "enrichment_requested_at",
    ):
        op.drop_column("procurement_lot_records", column)
