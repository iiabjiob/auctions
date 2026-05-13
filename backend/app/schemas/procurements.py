from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class ProcurementSourceInfo(BaseModel):
    code: str
    title: str
    website: str
    enabled: bool = True


class ProcurementLotItem(BaseModel):
    source: str = "zakupki"
    external_id: str
    registry_number: str
    law: str | None = None
    title: str | None = None
    status: str | None = None
    customer_name: str | None = None
    customer_inn: str | None = None
    organizer_name: str | None = None
    procedure_type: str | None = None
    platform_name: str | None = None
    region: str | None = None
    delivery_region: str | None = None
    delivery_address: str | None = None
    initial_price: str | None = None
    initial_price_value: Decimal | None = None
    currency: str | None = None
    publication_date: str | None = None
    application_deadline: str | None = None
    notice_url: str | None = None
    print_url: str | None = None
    documents_url: str | None = None
    specification_url: str | None = None
    documentation_present: bool | None = None
    raw_fields: dict[str, str] = Field(default_factory=dict)


class ProcurementAttractiveness(BaseModel):
    score: int
    level: str
    reasons: list[str]


class ProcurementLotResponse(BaseModel):
    id: int
    source: str
    external_id: str
    registry_number: str
    law: str | None
    title: str | None
    status: str | None
    customer_name: str | None
    customer_inn: str | None
    organizer_name: str | None
    procedure_type: str | None
    platform_name: str | None
    region: str | None
    delivery_region: str | None
    delivery_address: str | None
    initial_price: str | None
    initial_price_value: Decimal | None
    currency: str | None
    publication_at: datetime | None
    application_deadline_at: datetime | None
    notice_url: str | None
    specification_url: str | None
    documents_url: str | None
    certificate_requirements: str | None
    documentation_present: bool | None
    is_new: bool
    category: str | None
    matched_keywords: list[str]
    excluded_keywords: list[str]
    filter_reason: str | None
    attractiveness: ProcurementAttractiveness
    workflow_status: str
    assignee: str | None
    comment: str | None
    final_decision: str | None
    rejection_reason: str | None
    bid_security_amount: Decimal | None
    contract_security_amount: Decimal | None
    prepayment_percent: Decimal | None
    payment_terms: str | None
    quantity: Decimal | None
    unit_nmck: Decimal | None
    cost_realistic: Decimal | None
    cost_cautious: Decimal | None
    net_profit: Decimal | None
    profitability: Decimal | None
    roi: Decimal | None
    cash_gap_peak: Decimal | None
    first_seen_at: datetime
    last_seen_at: datetime


class ProcurementLotListResponse(BaseModel):
    items: list[ProcurementLotResponse]
    total: int
    page: int
    page_size: int


class ProcurementSyncResult(BaseModel):
    source: str
    fetched: int
    created: int
    updated: int
    unchanged: int
    status_changed: int


class ProcurementListDebugResponse(BaseModel):
    items: list[ProcurementLotItem]
    raw: dict[str, Any] | None = None
