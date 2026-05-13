from __future__ import annotations

import hashlib
import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.procurement import ProcurementLotRecord, ProcurementSourceState
from app.schemas.procurements import ProcurementLotItem, ProcurementSyncResult
from app.services.procurement_classification import ProcurementClassification, classify_procurement_lot
from app.services.procurement_scoring import apply_procurement_score
from app.services.procurement_values import parse_scraped_datetime
from app.services.zakupki_scraper import fetch_procurement_list, source_info


logger = logging.getLogger(__name__)
NEWNESS_WINDOW_DAYS = 3


@dataclass(slots=True)
class PreparedProcurementLot:
    item: ProcurementLotItem
    classification: ProcurementClassification
    normalized_item: dict
    content_hash: str


async def sync_zakupki_procurements(session: AsyncSession, *, limit: int | None = 100) -> ProcurementSyncResult:
    info = source_info()
    now = datetime.now(UTC)
    source_state = await session.get(ProcurementSourceState, info.code)
    if source_state is None:
        source_state = ProcurementSourceState(
            code=info.code,
            title=info.title,
            website=info.website,
            enabled=info.enabled,
        )
        session.add(source_state)
    else:
        source_state.title = info.title
        source_state.website = info.website
        source_state.enabled = info.enabled
    source_state.last_synced_at = now

    result = ProcurementSyncResult(source=info.code, fetched=0, created=0, updated=0, unchanged=0, status_changed=0)
    items = await asyncio.to_thread(fetch_procurement_list, limit=limit)
    for item in items:
        result.fetched += 1
        prepared = prepare_procurement_lot(item)
        record = await _find_record(session, source_code=info.code, external_id=item.external_id)
        publication_at = parse_scraped_datetime(item.publication_date)
        deadline_at = parse_scraped_datetime(item.application_deadline)
        is_new = _is_new(publication_at=publication_at, observed_at=now)

        if record is None:
            record = ProcurementLotRecord(
                source_code=info.code,
                external_id=item.external_id,
                registry_number=item.registry_number,
                law=item.law,
                title=item.title,
                status=item.status,
                customer_name=item.customer_name,
                customer_inn=item.customer_inn,
                organizer_name=item.organizer_name,
                procedure_type=item.procedure_type,
                platform_name=item.platform_name,
                region=item.region,
                delivery_region=item.delivery_region,
                delivery_address=item.delivery_address,
                initial_price=item.initial_price,
                initial_price_value=item.initial_price_value,
                currency=item.currency,
                publication_at=publication_at,
                application_deadline_at=deadline_at,
                notice_url=item.notice_url,
                print_url=item.print_url,
                specification_url=item.specification_url,
                documents_url=item.documents_url,
                documentation_present=item.documentation_present,
                content_hash=prepared.content_hash,
                first_seen_at=now,
                last_seen_at=now,
                is_new=is_new,
                category=prepared.classification.category,
                matched_keywords=prepared.classification.matched_keywords,
                excluded_keywords=prepared.classification.excluded_keywords,
                filter_reason=prepared.classification.filter_reason,
                attractiveness_score=0,
                attractiveness_level="reject",
                attractiveness_reasons=[],
                normalized_item=prepared.normalized_item,
                raw_item=item.model_dump(mode="json"),
            )
            apply_procurement_score(record, current_time=now)
            session.add(record)
            result.created += 1
            continue

        status_changed = record.status != item.status
        content_changed = record.content_hash != prepared.content_hash
        record.last_seen_at = now
        record.registry_number = item.registry_number
        record.law = item.law
        record.title = item.title
        record.status = item.status
        record.customer_name = item.customer_name
        record.customer_inn = item.customer_inn
        record.organizer_name = item.organizer_name
        record.procedure_type = item.procedure_type
        record.platform_name = item.platform_name
        record.region = item.region
        record.delivery_region = item.delivery_region
        record.delivery_address = item.delivery_address
        record.initial_price = item.initial_price
        record.initial_price_value = item.initial_price_value
        record.currency = item.currency
        record.publication_at = publication_at
        record.application_deadline_at = deadline_at
        record.notice_url = item.notice_url
        record.print_url = item.print_url
        record.specification_url = item.specification_url
        record.documents_url = item.documents_url
        record.documentation_present = item.documentation_present
        record.is_new = _is_new(publication_at=publication_at or record.first_seen_at, observed_at=now)
        record.category = prepared.classification.category
        record.matched_keywords = prepared.classification.matched_keywords
        record.excluded_keywords = prepared.classification.excluded_keywords
        record.filter_reason = prepared.classification.filter_reason
        record.normalized_item = prepared.normalized_item
        record.raw_item = item.model_dump(mode="json")
        apply_procurement_score(record, current_time=now)
        if status_changed:
            record.status_changed_at = now
            result.status_changed += 1
        if content_changed:
            record.content_hash = prepared.content_hash
            result.updated += 1
        else:
            result.unchanged += 1

    await session.commit()
    logger.info("Zakupki procurement sync finished: %s", result.model_dump(mode="json"))
    return result


def prepare_procurement_lot(item: ProcurementLotItem) -> PreparedProcurementLot:
    classification = classify_procurement_lot(item)
    normalized = item.model_dump(mode="json")
    normalized["classification"] = {
        "category": classification.category,
        "matched_keywords": classification.matched_keywords,
        "excluded_keywords": classification.excluded_keywords,
        "filter_reason": classification.filter_reason,
        "is_relevant": classification.is_relevant,
    }
    content_hash = hashlib.sha256(
        json.dumps(normalized, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    return PreparedProcurementLot(
        item=item,
        classification=classification,
        normalized_item=normalized,
        content_hash=content_hash,
    )


async def _find_record(session: AsyncSession, *, source_code: str, external_id: str) -> ProcurementLotRecord | None:
    result = await session.execute(
        select(ProcurementLotRecord).where(
            ProcurementLotRecord.source_code == source_code,
            ProcurementLotRecord.external_id == external_id,
        )
    )
    return result.scalar_one_or_none()


def _is_new(*, publication_at: datetime | None, observed_at: datetime) -> bool:
    if publication_at is None:
        return True
    return (observed_at - publication_at).days <= NEWNESS_WINDOW_DAYS
