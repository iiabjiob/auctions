from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.procurement import (
    ProcurementLotDetailCache,
    ProcurementLotDetailObservation,
    ProcurementLotRecord,
    ProcurementSourceState,
)
from app.services.procurement_grid_state import bump_procurement_lot_dataset_version
from app.services.procurement_notifications import enqueue_procurement_telegram_notifications
from app.services.procurement_scoring import apply_procurement_score
from app.services.procurement_sources import get_procurement_source_provider


DEFAULT_PROCUREMENT_ENRICHMENT_CANDIDATE_LIMIT = 25
PROCUREMENT_ENRICHMENT_CLAIM_SECONDS = 15 * 60
PROCUREMENT_ENRICHMENT_BACKOFF_BASE_SECONDS = 30 * 60
PROCUREMENT_ENRICHMENT_BACKOFF_MAX_SECONDS = 24 * 60 * 60
PROCUREMENT_ENRICHMENT_MAX_ATTEMPTS = 3
PROCUREMENT_ENRICHMENT_WORKER_ID = "procurement-enrichment-worker"


class ProcurementEnrichmentRequirementEvaluation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    needs_enrichment: bool
    missing_fields: list[str] = Field(default_factory=list)
    reason_category: str = "ready_for_scoring"


class ProcurementEnrichmentExecutionResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_count: int
    processed_count: int
    fetched_count: int
    updated_count: int
    still_missing_count: int
    skipped_count: int
    candidate_record_ids: list[int] = Field(default_factory=list)
    completed_record_ids: list[int] = Field(default_factory=list)


def classify_procurement_enrichment(record: ProcurementLotRecord) -> ProcurementEnrichmentRequirementEvaluation:
    missing_fields: list[str] = []
    if not record.notice_url:
        missing_fields.append("notice_url")
    if not record.documents_url and not record.specification_url and not record.documentation_present:
        missing_fields.append("documents")
    if not record.certificate_requirements:
        missing_fields.append("certificate_requirements")
    if not record.payment_terms:
        missing_fields.append("payment_terms")
    if not record.delivery_address and not record.delivery_region:
        missing_fields.append("delivery")
    return ProcurementEnrichmentRequirementEvaluation(
        needs_enrichment=bool(missing_fields) and bool(record.notice_url or record.documents_url),
        missing_fields=missing_fields,
        reason_category="missing_procurement_detail" if missing_fields else "ready_for_scoring",
    )


def schedule_procurement_lot_enrichment(
    record: ProcurementLotRecord,
    evaluation: ProcurementEnrichmentRequirementEvaluation,
    *,
    requested_at: datetime | None = None,
    force: bool = False,
) -> bool:
    if not evaluation.needs_enrichment:
        return False
    if record.enrichment_requested_at is not None and not force:
        return False
    record.enrichment_requested_at = requested_at or datetime.now(UTC)
    record.enrichment_requested_reason = evaluation.reason_category
    if force:
        record.next_enrichment_attempt_at = None
        record.last_enrichment_error = None
    return True


async def list_procurement_enrichment_candidates(
    session: AsyncSession,
    *,
    source_code: str | None = None,
    current_time: datetime | None = None,
    limit: int = DEFAULT_PROCUREMENT_ENRICHMENT_CANDIDATE_LIMIT,
) -> list[ProcurementLotRecord]:
    current_time = current_time or datetime.now(UTC)
    statement = (
        select(ProcurementLotRecord)
        .join(ProcurementSourceState, ProcurementSourceState.code == ProcurementLotRecord.source_code)
        .where(ProcurementLotRecord.enrichment_requested_at.is_not(None))
        .where(
            or_(
                ProcurementLotRecord.next_enrichment_attempt_at.is_(None),
                ProcurementLotRecord.next_enrichment_attempt_at <= current_time,
            )
        )
        .where(
            or_(
                ProcurementLotRecord.enrichment_claimed_at.is_(None),
                ProcurementLotRecord.enrichment_claim_expires_at.is_(None),
                ProcurementLotRecord.enrichment_claim_expires_at <= current_time,
            )
        )
        .where(ProcurementLotRecord.enrichment_attempt_count < PROCUREMENT_ENRICHMENT_MAX_ATTEMPTS)
        .where(ProcurementSourceState.enabled.is_(True))
        .order_by(
            ProcurementLotRecord.attractiveness_score.desc(),
            ProcurementLotRecord.application_deadline_at.asc().nulls_last(),
            ProcurementLotRecord.enrichment_requested_at.asc(),
            ProcurementLotRecord.id.asc(),
        )
    )
    if source_code:
        statement = statement.where(ProcurementLotRecord.source_code == source_code)
    if limit > 0:
        statement = statement.limit(limit)
    return list((await session.scalars(statement)).all())


async def execute_procurement_enrichment_candidates(
    session: AsyncSession,
    *,
    limit: int = DEFAULT_PROCUREMENT_ENRICHMENT_CANDIDATE_LIMIT,
    item_pause_seconds: float = 0.0,
    current_time: datetime | None = None,
) -> ProcurementEnrichmentExecutionResult:
    current_time = current_time or datetime.now(UTC)
    candidates = await list_procurement_enrichment_candidates(session, current_time=current_time, limit=limit)
    candidate_ids = [int(record.id) for record in candidates if record.id is not None]
    processed_count = 0
    fetched_count = 0
    updated_count = 0
    still_missing_count = 0
    skipped_count = 0
    completed_ids: list[int] = []

    for record in candidates:
        processed_count += 1
        _claim_record(record, current_time=current_time)
        try:
            changed = await enrich_procurement_lot_record(session, record, current_time=current_time)
            fetched_count += 1
            if changed:
                updated_count += 1
            evaluation = classify_procurement_enrichment(record)
            if evaluation.needs_enrichment:
                still_missing_count += 1
                _mark_attempt_failed(record, current_time=current_time, reason=evaluation.reason_category)
            else:
                _mark_enrichment_completed(record)
                if record.id is not None:
                    completed_ids.append(int(record.id))
            await session.flush()
        except Exception as error:
            _mark_attempt_failed(record, current_time=current_time, reason=str(error)[:2000])
            skipped_count += 1
            await session.flush()
        if item_pause_seconds > 0:
            await asyncio.sleep(item_pause_seconds)

    return ProcurementEnrichmentExecutionResult(
        candidate_count=len(candidates),
        processed_count=processed_count,
        fetched_count=fetched_count,
        updated_count=updated_count,
        still_missing_count=still_missing_count,
        skipped_count=skipped_count,
        candidate_record_ids=candidate_ids,
        completed_record_ids=completed_ids,
    )


async def enrich_procurement_lot_record(
    session: AsyncSession,
    record: ProcurementLotRecord,
    *,
    current_time: datetime | None = None,
) -> bool:
    current_time = current_time or datetime.now(UTC)
    provider = get_procurement_source_provider(record.source_code)
    detail_payload = await asyncio.to_thread(
        lambda: provider.get_lot_detail(
            record.external_id,
            notice_url=record.notice_url,
            documents_url=record.documents_url,
        )
    )
    documents = await asyncio.to_thread(
        lambda: provider.get_documents(
            record.external_id,
            documents_url=record.documents_url or record.specification_url,
            notice_url=record.notice_url,
        )
    )
    detail_payload = detail_payload or {}
    documents = documents or []
    changed = await _upsert_detail_cache(
        session,
        record,
        detail_payload=detail_payload,
        documents=documents,
        fetched_at=current_time,
    )
    _apply_detail_to_record(record, detail_payload=detail_payload, documents=documents, observed_at=current_time)
    apply_procurement_score(record, current_time=current_time)
    await enqueue_procurement_telegram_notifications(session, record, now=current_time)
    if changed:
        await bump_procurement_lot_dataset_version(
            session,
            record,
            event_type="row_updated",
            payload={"source": "procurement_enrichment", "changed_fields": ["detail_cache", "documents"]},
        )
    return changed


async def _upsert_detail_cache(
    session: AsyncSession,
    record: ProcurementLotRecord,
    *,
    detail_payload: dict,
    documents: list[dict],
    fetched_at: datetime,
) -> bool:
    content_hash = hashlib.sha256(
        json.dumps({"detail": detail_payload, "documents": documents}, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    cache = await session.scalar(
        select(ProcurementLotDetailCache)
        .where(ProcurementLotDetailCache.procurement_lot_record_id == record.id)
        .with_for_update()
    )
    changed = cache is None or cache.content_hash != content_hash
    if cache is None:
        cache = ProcurementLotDetailCache(
            procurement_lot_record_id=int(record.id),
            content_hash=content_hash,
            detail_payload=detail_payload,
            documents=documents,
            fetched_at=fetched_at,
        )
        session.add(cache)
    else:
        cache.content_hash = content_hash
        cache.detail_payload = detail_payload
        cache.documents = documents
        cache.fetched_at = fetched_at
    if changed:
        session.add(
            ProcurementLotDetailObservation(
                procurement_lot_record_id=int(record.id),
                content_hash=content_hash,
                detail_payload=detail_payload,
                documents=documents,
                observed_at=fetched_at,
            )
        )
    return changed


def _apply_detail_to_record(
    record: ProcurementLotRecord,
    *,
    detail_payload: dict,
    documents: list[dict],
    observed_at: datetime,
) -> None:
    fields = detail_payload.get("fields") if isinstance(detail_payload, dict) else None
    fields = fields if isinstance(fields, dict) else {}
    record.documentation_present = record.documentation_present or bool(documents)
    if documents and not record.documents_url:
        record.documents_url = str(documents[0].get("source_url") or documents[0].get("url") or "")
    record.certificate_requirements = record.certificate_requirements or _first_field(
        fields,
        "Требования к участникам",
        "Требования",
        "Сертификат",
        "Лицензия",
    )
    record.payment_terms = record.payment_terms or _first_field(fields, "Порядок оплаты", "Условия оплаты", "Оплата")
    record.delivery_address = record.delivery_address or _first_field(fields, "Место поставки", "Адрес поставки")
    record.raw_item = {**(record.raw_item or {}), "detail": detail_payload, "documents": documents}
    record.last_seen_at = observed_at


def _first_field(fields: dict, *labels: str) -> str | None:
    for label in labels:
        label_lower = label.lower()
        for key, value in fields.items():
            if label_lower in str(key).lower() and value:
                return str(value)
    return None


def _claim_record(record: ProcurementLotRecord, *, current_time: datetime) -> None:
    record.enrichment_claimed_at = current_time
    record.enrichment_claimed_by = PROCUREMENT_ENRICHMENT_WORKER_ID
    record.enrichment_claim_expires_at = current_time + timedelta(seconds=PROCUREMENT_ENRICHMENT_CLAIM_SECONDS)


def _mark_attempt_failed(record: ProcurementLotRecord, *, current_time: datetime, reason: str) -> None:
    record.last_enrichment_attempt_at = current_time
    record.enrichment_attempt_count = int(record.enrichment_attempt_count or 0) + 1
    backoff_seconds = min(
        PROCUREMENT_ENRICHMENT_BACKOFF_MAX_SECONDS,
        PROCUREMENT_ENRICHMENT_BACKOFF_BASE_SECONDS * (2 ** max(0, record.enrichment_attempt_count - 1)),
    )
    record.next_enrichment_attempt_at = current_time + timedelta(seconds=backoff_seconds)
    record.last_enrichment_error = reason
    record.enrichment_claimed_at = None
    record.enrichment_claimed_by = None
    record.enrichment_claim_expires_at = None


def _mark_enrichment_completed(record: ProcurementLotRecord) -> None:
    record.enrichment_requested_at = None
    record.enrichment_requested_reason = None
    record.next_enrichment_attempt_at = None
    record.last_enrichment_error = None
    record.enrichment_claimed_at = None
    record.enrichment_claimed_by = None
    record.enrichment_claim_expires_at = None
