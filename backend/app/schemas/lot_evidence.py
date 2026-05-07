from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LotPriceFacts(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    initial_price: Decimal | None = None
    current_price: Decimal | None = None
    minimum_price: Decimal | None = None
    market_value: Decimal | None = None
    currency: str | None = None


class LotLocationFacts(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    region: str | None = None
    city: str | None = None
    address: str | None = None
    coordinates: str | None = None


class LotCategoryFacts(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    category: str | None = None
    model_category: str | None = None
    lot_name: str | None = None
    status: str | None = None


class LotLegalFacts(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    has_documents: bool = False
    has_photos: bool = False
    document_count: int = 0
    media_document_count: int = 0
    exclusion_signals: tuple[str, ...] = Field(default_factory=tuple)
    legal_risk_signals: tuple[str, ...] = Field(default_factory=tuple)


class LotDeadlineFacts(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    application_start: str | None = None
    application_deadline: str | None = None
    auction_date: str | None = None
    hours_to_deadline: int | None = None


class LotConstraintFacts(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    inspection_order: str | None = None
    description_present: bool = False
    price_schedule_steps: int = 0


class LotFreshnessFacts(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    is_new: bool = False
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    status_changed_at: datetime | None = None
    detail_fetched_at: datetime | None = None


class LotEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_code: str
    auction_external_id: str
    lot_external_id: str
    lot_number: str | None = None
    content_hash: str | None = None
    detail_content_hash: str | None = None
    price: LotPriceFacts = Field(default_factory=LotPriceFacts)
    location: LotLocationFacts = Field(default_factory=LotLocationFacts)
    category: LotCategoryFacts = Field(default_factory=LotCategoryFacts)
    legal: LotLegalFacts = Field(default_factory=LotLegalFacts)
    deadlines: LotDeadlineFacts = Field(default_factory=LotDeadlineFacts)
    constraints: LotConstraintFacts = Field(default_factory=LotConstraintFacts)
    freshness: LotFreshnessFacts = Field(default_factory=LotFreshnessFacts)

    def canonical_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


def build_lot_evidence_hash(evidence: LotEvidence) -> str:
    payload = evidence.canonical_payload()
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
