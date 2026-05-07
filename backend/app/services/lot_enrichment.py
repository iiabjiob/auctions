from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.auction import AuctionLotDetailCache, AuctionLotRecord
from app.schemas.lot_evidence import LotEvidence
from app.services.lot_evidence import build_lot_evidence


class LotEnrichmentRequirementEvaluation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    needs_enrichment: bool
    missing_fields: list[str] = Field(default_factory=list)
    reason_category: str = "ready_for_scoring"


def evaluate_lot_enrichment_requirements(evidence: LotEvidence) -> LotEnrichmentRequirementEvaluation:
    missing_fields: list[str] = []
    if not _has_price_facts(evidence):
        missing_fields.append("price")
    if not _has_location_facts(evidence):
        missing_fields.append("location")
    if not _has_category_facts(evidence):
        missing_fields.append("category")
    if not _has_deadline_facts(evidence):
        missing_fields.append("deadline")

    needs_enrichment = bool(missing_fields)
    return LotEnrichmentRequirementEvaluation(
        needs_enrichment=needs_enrichment,
        missing_fields=missing_fields,
        reason_category="missing_first_pass_evidence" if needs_enrichment else "ready_for_scoring",
    )


def classify_lot_enrichment(
    record: AuctionLotRecord,
    detail_cache: AuctionLotDetailCache | None = None,
) -> LotEnrichmentRequirementEvaluation:
    return evaluate_lot_enrichment_requirements(build_lot_evidence(record, detail_cache))


def schedule_lot_enrichment(
    record: AuctionLotRecord,
    evaluation: LotEnrichmentRequirementEvaluation,
    *,
    requested_at: datetime | None = None,
    force: bool = False,
) -> bool:
    if evaluation.needs_enrichment:
        next_requested_at = requested_at or datetime.now(UTC)
        if not force and record.enrichment_requested_at is not None:
            return False
        record.enrichment_requested_at = next_requested_at
        return True
    if record.enrichment_requested_at is None:
        return False
    record.enrichment_requested_at = None
    return True


def _has_price_facts(evidence: LotEvidence) -> bool:
    return any(
        [
            evidence.price.current_price is not None,
            evidence.price.initial_price is not None,
            evidence.price.minimum_price is not None,
            evidence.price.market_value is not None,
        ]
    )


def _has_location_facts(evidence: LotEvidence) -> bool:
    return any(
        [
            _has_text(evidence.location.region),
            _has_text(evidence.location.city),
            _has_text(evidence.location.address),
            _has_text(evidence.location.coordinates),
        ]
    )


def _has_category_facts(evidence: LotEvidence) -> bool:
    return any(
        [
            _has_text(evidence.category.category),
            _has_text(evidence.category.model_category),
        ]
    )


def _has_deadline_facts(evidence: LotEvidence) -> bool:
    return any(
        [
            _has_text(evidence.deadlines.application_deadline),
            _has_text(evidence.deadlines.auction_date),
            _has_text(evidence.deadlines.application_start),
            evidence.deadlines.hours_to_deadline is not None,
        ]
    )


def _has_text(value: str | None) -> bool:
    return isinstance(value, str) and bool(value.strip())
