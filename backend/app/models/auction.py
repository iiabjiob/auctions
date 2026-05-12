from __future__ import annotations

from datetime import datetime

from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.database import Base


class AuctionSourceState(Base):
    __tablename__ = "auction_source_states"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    website: Mapped[str] = mapped_column(String(512), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sync_cursor: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    lots: Mapped[list["AuctionLotRecord"]] = relationship(back_populates="source_state")


class AuctionLotRecord(Base):
    __tablename__ = "auction_lot_records"
    __table_args__ = (
        UniqueConstraint("source_code", "auction_external_id", "lot_external_id"),
        Index("ix_auction_lot_records_lifecycle_status_rating_score", "lifecycle_status", "rating_score"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_code: Mapped[str] = mapped_column(ForeignKey("auction_source_states.code"), nullable=False, index=True)
    auction_external_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    lot_external_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    auction_number: Mapped[str | None] = mapped_column(String(128), index=True)
    lot_number: Mapped[str | None] = mapped_column(String(128))
    lot_name: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(String(255), index=True)
    initial_price: Mapped[str | None] = mapped_column(String(128))
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_new: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    rating_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    rating_level: Mapped[str] = mapped_column(String(32), nullable=False, default="low")
    scoring_version: Mapped[str] = mapped_column(String(64), nullable=False, default="unscored", index=True)
    scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    score_input_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    score_breakdown: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    search_text: Mapped[str | None] = mapped_column(Text)
    publication_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    application_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    application_deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    auction_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    lifecycle_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="active",
        server_default=text("'active'"),
        index=True,
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    archive_reason: Mapped[str | None] = mapped_column(Text)
    actuality_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    enrichment_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_enrichment_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    enrichment_attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_enrichment_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_enrichment_error: Mapped[str | None] = mapped_column(Text)
    enrichment_claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    enrichment_claimed_by: Mapped[str | None] = mapped_column(String(255), index=True)
    enrichment_claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    datagrid_row: Mapped[dict] = mapped_column(JSONB, nullable=False)
    normalized_item: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    source_state: Mapped[AuctionSourceState] = relationship(back_populates="lots")
    observations: Mapped[list["AuctionLotObservation"]] = relationship(back_populates="lot")
    ai_analyses: Mapped[list["AuctionLotAiAnalysis"]] = relationship(back_populates="lot")
    decision_reports: Mapped[list["AuctionLotDecisionReport"]] = relationship(back_populates="lot")
    telegram_notifications: Mapped[list["TelegramNotificationOutbox"]] = relationship(back_populates="lot")


class AuctionLotObservation(Base):
    __tablename__ = "auction_lot_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lot_record_id: Mapped[int] = mapped_column(ForeignKey("auction_lot_records.id"), nullable=False, index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str | None] = mapped_column(String(255), index=True)
    datagrid_row: Mapped[dict] = mapped_column(JSONB, nullable=False)
    normalized_item: Mapped[dict] = mapped_column(JSONB, nullable=False)

    lot: Mapped[AuctionLotRecord] = relationship(back_populates="observations")


class AuctionLotDetailCache(Base):
    __tablename__ = "auction_lot_detail_caches"
    __table_args__ = (UniqueConstraint("lot_record_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lot_record_id: Mapped[int] = mapped_column(ForeignKey("auction_lot_records.id"), nullable=False, index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    lot_detail: Mapped[dict] = mapped_column(JSONB, nullable=False)
    auction_detail: Mapped[dict | None] = mapped_column(JSONB)
    documents: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AuctionLotDetailObservation(Base):
    __tablename__ = "auction_lot_detail_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lot_record_id: Mapped[int] = mapped_column(ForeignKey("auction_lot_records.id"), nullable=False, index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    lot_detail: Mapped[dict] = mapped_column(JSONB, nullable=False)
    auction_detail: Mapped[dict | None] = mapped_column(JSONB)
    documents: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)


class AuctionLotWorkItem(Base):
    __tablename__ = "auction_lot_work_items"
    __table_args__ = (UniqueConstraint("lot_record_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lot_record_id: Mapped[int] = mapped_column(ForeignKey("auction_lot_records.id"), nullable=False, index=True)
    decision_status: Mapped[str | None] = mapped_column(String(64))
    assignee: Mapped[str | None] = mapped_column(String(255))
    comment: Mapped[str | None] = mapped_column(Text)
    inspection_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    inspection_result: Mapped[str | None] = mapped_column(Text)
    final_decision: Mapped[str | None] = mapped_column(String(64))
    investor: Mapped[str | None] = mapped_column(String(255))
    deposit_status: Mapped[str | None] = mapped_column(String(64))
    application_status: Mapped[str | None] = mapped_column(String(64))
    exclude_from_analysis: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    exclusion_reason: Mapped[str | None] = mapped_column(Text)
    category_override: Mapped[str | None] = mapped_column(String(255))
    max_purchase_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    market_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    platform_fee: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    delivery_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    dismantling_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    repair_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    storage_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    legal_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    other_costs: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    target_profit: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    analogs: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AuctionLotDecisionReport(Base):
    __tablename__ = "auction_lot_decision_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lot_record_id: Mapped[int] = mapped_column(ForeignKey("auction_lot_records.id"), nullable=False, index=True)
    profile_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    report_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    decision_level: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    recommendation: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    notification_should_send: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    report_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    lot: Mapped[AuctionLotRecord] = relationship(back_populates="decision_reports")
    telegram_notifications: Mapped[list["TelegramNotificationOutbox"]] = relationship(back_populates="decision_report")


class TelegramNotificationOutbox(Base):
    __tablename__ = "telegram_notification_outbox"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_telegram_notification_outbox_dedupe_key"),
        CheckConstraint(
            "status IN ('pending', 'sent', 'failed', 'skipped')",
            name="ck_telegram_notification_outbox_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lot_record_id: Mapped[int] = mapped_column(
        ForeignKey("auction_lot_records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    decision_report_id: Mapped[int] = mapped_column(
        ForeignKey("auction_lot_decision_reports.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dedupe_key: Mapped[str] = mapped_column(String(128), nullable=False)
    cooldown_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    priority: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    message_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    report_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
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

    lot: Mapped[AuctionLotRecord] = relationship(back_populates="telegram_notifications")
    decision_report: Mapped[AuctionLotDecisionReport] = relationship(back_populates="telegram_notifications")


class AuctionLotAiAnalysis(Base):
    __tablename__ = "auction_lot_ai_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lot_record_id: Mapped[int] = mapped_column(ForeignKey("auction_lot_records.id"), nullable=False, index=True)
    deterministic_scoring_version: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    deterministic_score: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    deterministic_rank: Mapped[int | None] = mapped_column(Integer)
    ai_score: Mapped[int | None] = mapped_column(Integer, index=True)
    ai_rank: Mapped[int | None] = mapped_column(Integer)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(128), nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    input_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    output_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    operator_feedback_status: Mapped[str | None] = mapped_column(String(32), index=True)
    operator_feedback_comment: Mapped[str | None] = mapped_column(Text)
    operator_feedback_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    operator_feedback_by: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    lot: Mapped[AuctionLotRecord] = relationship(back_populates="ai_analyses")
