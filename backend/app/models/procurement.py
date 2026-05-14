from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, event, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.database import Base


class ProcurementSourceState(Base):
    __tablename__ = "procurement_source_states"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    website: Mapped[str] = mapped_column(String(512), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    lots: Mapped[list["ProcurementLotRecord"]] = relationship(back_populates="source_state")


class ProcurementSourceSyncState(Base):
    __tablename__ = "procurement_source_sync_states"

    source_code: Mapped[str] = mapped_column(ForeignKey("procurement_source_states.code"), primary_key=True)
    last_sync_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_sync_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_successful_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_sync_result: Mapped[str | None] = mapped_column(String(32), index=True)
    last_sync_error: Mapped[str | None] = mapped_column(Text)
    last_sync_error_code: Mapped[str | None] = mapped_column(String(64), index=True)
    last_sync_fetched: Mapped[int | None] = mapped_column(Integer)
    last_sync_created: Mapped[int | None] = mapped_column(Integer)
    last_sync_updated: Mapped[int | None] = mapped_column(Integer)
    last_sync_unchanged: Mapped[int | None] = mapped_column(Integer)
    last_sync_status_changed: Mapped[int | None] = mapped_column(Integer)
    last_sync_parser_failures: Mapped[int | None] = mapped_column(Integer)
    last_sync_missing_critical_fields: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    cursor_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    cursor_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    parser_version: Mapped[str | None] = mapped_column(String(64), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    source_state: Mapped[ProcurementSourceState] = relationship()


class ProcurementSourceSyncRun(Base):
    __tablename__ = "procurement_source_sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_code: Mapped[str] = mapped_column(ForeignKey("procurement_source_states.code"), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    result: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    fetched_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unchanged_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status_changed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    parser_failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    missing_critical_fields: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    parser_version: Mapped[str | None] = mapped_column(String(64), index=True)
    error_code: Mapped[str | None] = mapped_column(String(64), index=True)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    source_state: Mapped[ProcurementSourceState] = relationship()


class ProcurementLotRecord(Base):
    __tablename__ = "procurement_lot_records"
    __table_args__ = (
        UniqueConstraint("source_code", "external_id", name="uq_procurement_lot_records_source_external_id"),
        Index("ix_procurement_lot_records_score_status", "attractiveness_score", "status"),
        Index("ix_procurement_lot_records_law_status", "law", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_code: Mapped[str] = mapped_column(ForeignKey("procurement_source_states.code"), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    registry_number: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    law: Mapped[str | None] = mapped_column(String(32), index=True)
    title: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(String(255), index=True)
    customer_name: Mapped[str | None] = mapped_column(Text)
    customer_inn: Mapped[str | None] = mapped_column(String(32), index=True)
    organizer_name: Mapped[str | None] = mapped_column(Text)
    procedure_type: Mapped[str | None] = mapped_column(String(255), index=True)
    platform_name: Mapped[str | None] = mapped_column(Text)
    region: Mapped[str | None] = mapped_column(String(255), index=True)
    delivery_region: Mapped[str | None] = mapped_column(String(255), index=True)
    delivery_address: Mapped[str | None] = mapped_column(Text)
    initial_price: Mapped[str | None] = mapped_column(String(128))
    initial_price_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), index=True)
    currency: Mapped[str | None] = mapped_column(String(16))
    publication_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    application_deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    notice_url: Mapped[str | None] = mapped_column(Text)
    print_url: Mapped[str | None] = mapped_column(Text)
    specification_url: Mapped[str | None] = mapped_column(Text)
    documents_url: Mapped[str | None] = mapped_column(Text)
    certificate_requirements: Mapped[str | None] = mapped_column(Text)
    documentation_present: Mapped[bool | None] = mapped_column(Boolean, index=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    is_new: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    category: Mapped[str | None] = mapped_column(String(64), index=True)
    matched_keywords: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    excluded_keywords: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    filter_reason: Mapped[str | None] = mapped_column(Text)
    attractiveness_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    attractiveness_level: Mapped[str] = mapped_column(String(32), nullable=False, default="low", index=True)
    attractiveness_reasons: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    scoring_version: Mapped[str | None] = mapped_column(String(32), index=True)
    scoring_input_hash: Mapped[str | None] = mapped_column(String(64))
    scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    enrichment_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    enrichment_requested_reason: Mapped[str | None] = mapped_column(String(64), index=True)
    last_enrichment_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    enrichment_attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_enrichment_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_enrichment_error: Mapped[str | None] = mapped_column(Text)
    enrichment_claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    enrichment_claimed_by: Mapped[str | None] = mapped_column(String(255), index=True)
    enrichment_claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    workflow_status: Mapped[str] = mapped_column(String(64), nullable=False, default="new", index=True)
    assignee: Mapped[str | None] = mapped_column(String(255), index=True)
    comment: Mapped[str | None] = mapped_column(Text)
    final_decision: Mapped[str | None] = mapped_column(String(64), index=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    bid_security_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    contract_security_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    prepayment_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    payment_terms: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 3))
    unit_nmck: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    cost_realistic: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    cost_cautious: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    net_profit: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), index=True)
    profitability: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), index=True)
    roi: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), index=True)
    cash_gap_peak: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    calculator_inputs: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    calculator_scenarios: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    search_text: Mapped[str | None] = mapped_column(Text)
    normalized_item: Mapped[dict] = mapped_column(JSONB, nullable=False)
    raw_item: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    source_state: Mapped[ProcurementSourceState] = relationship(back_populates="lots")
    observations: Mapped[list["ProcurementLotObservation"]] = relationship(back_populates="lot")
    detail_cache: Mapped["ProcurementLotDetailCache | None"] = relationship(back_populates="lot")
    telegram_notifications: Mapped[list["ProcurementTelegramNotificationOutbox"]] = relationship(back_populates="lot")


class ProcurementLotObservation(Base):
    __tablename__ = "procurement_lot_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    procurement_lot_record_id: Mapped[int] = mapped_column(
        ForeignKey("procurement_lot_records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str | None] = mapped_column(String(255), index=True)
    normalized_item: Mapped[dict] = mapped_column(JSONB, nullable=False)
    raw_item: Mapped[dict] = mapped_column(JSONB, nullable=False)

    lot: Mapped[ProcurementLotRecord] = relationship(back_populates="observations")


class ProcurementLotDetailCache(Base):
    __tablename__ = "procurement_lot_detail_caches"
    __table_args__ = (UniqueConstraint("procurement_lot_record_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    procurement_lot_record_id: Mapped[int] = mapped_column(
        ForeignKey("procurement_lot_records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    detail_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    documents: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    lot: Mapped[ProcurementLotRecord] = relationship(back_populates="detail_cache")


class ProcurementLotDetailObservation(Base):
    __tablename__ = "procurement_lot_detail_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    procurement_lot_record_id: Mapped[int] = mapped_column(
        ForeignKey("procurement_lot_records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    detail_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    documents: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)


class ProcurementSourceHttpExchange(Base):
    __tablename__ = "procurement_source_http_exchanges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_code: Mapped[str] = mapped_column(ForeignKey("procurement_source_states.code"), nullable=False, index=True)
    operation: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer, index=True)
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)
    request_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    response_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_type: Mapped[str | None] = mapped_column(String(128), index=True)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    source_state: Mapped[ProcurementSourceState] = relationship()


class ProcurementTelegramNotificationOutbox(Base):
    __tablename__ = "procurement_telegram_notification_outbox"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_procurement_telegram_outbox_dedupe_key"),
        Index(
            "uq_procurement_telegram_outbox_lot_event_delivery",
            "procurement_lot_record_id",
            "event_type",
            unique=True,
            postgresql_where=text("status IN ('pending', 'sent')"),
        ),
        CheckConstraint(
            "status IN ('pending', 'sent', 'failed', 'skipped')",
            name="ck_procurement_telegram_outbox_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    procurement_lot_record_id: Mapped[int] = mapped_column(
        ForeignKey("procurement_lot_records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    telegram_chat_id: Mapped[str | None] = mapped_column(String(128))
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False)
    cooldown_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    priority: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    message_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    event_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    lot: Mapped[ProcurementLotRecord] = relationship(back_populates="telegram_notifications")


@event.listens_for(ProcurementLotRecord, "before_insert")
@event.listens_for(ProcurementLotRecord, "before_update")
def _sync_procurement_lot_search_text(_mapper, _connection, target: ProcurementLotRecord) -> None:
    parts = [
        target.registry_number,
        target.law,
        target.title,
        target.status,
        target.customer_name,
        target.customer_inn,
        target.organizer_name,
        target.procedure_type,
        target.platform_name,
        target.region,
        target.delivery_region,
        target.delivery_address,
        target.category,
        target.workflow_status,
        target.assignee,
    ]
    target.search_text = " ".join(part.strip() for part in parts if isinstance(part, str) and part.strip()) or None
