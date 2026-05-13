from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, event, func
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
    organizer_name: Mapped[str | None] = mapped_column(Text)
    procedure_type: Mapped[str | None] = mapped_column(String(255), index=True)
    platform_name: Mapped[str | None] = mapped_column(Text)
    region: Mapped[str | None] = mapped_column(String(255), index=True)
    initial_price: Mapped[str | None] = mapped_column(String(128))
    initial_price_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), index=True)
    currency: Mapped[str | None] = mapped_column(String(16))
    publication_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    application_deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    notice_url: Mapped[str | None] = mapped_column(Text)
    print_url: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    is_new: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    attractiveness_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    attractiveness_level: Mapped[str] = mapped_column(String(32), nullable=False, default="low", index=True)
    attractiveness_reasons: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    search_text: Mapped[str | None] = mapped_column(Text)
    normalized_item: Mapped[dict] = mapped_column(JSONB, nullable=False)
    raw_item: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    source_state: Mapped[ProcurementSourceState] = relationship(back_populates="lots")


@event.listens_for(ProcurementLotRecord, "before_insert")
@event.listens_for(ProcurementLotRecord, "before_update")
def _sync_procurement_lot_search_text(_mapper, _connection, target: ProcurementLotRecord) -> None:
    parts = [
        target.registry_number,
        target.law,
        target.title,
        target.status,
        target.customer_name,
        target.organizer_name,
        target.procedure_type,
        target.platform_name,
        target.region,
    ]
    target.search_text = " ".join(part.strip() for part in parts if isinstance(part, str) and part.strip()) or None
