from __future__ import annotations

from datetime import datetime

from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    lots: Mapped[list["AuctionLotRecord"]] = relationship(back_populates="source_state")


class AuctionLotRecord(Base):
    __tablename__ = "auction_lot_records"
    __table_args__ = (UniqueConstraint("source_code", "auction_external_id", "lot_external_id"),)

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
    datagrid_row: Mapped[dict] = mapped_column(JSONB, nullable=False)
    normalized_item: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    source_state: Mapped[AuctionSourceState] = relationship(back_populates="lots")
    observations: Mapped[list["AuctionLotObservation"]] = relationship(back_populates="lot")


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
