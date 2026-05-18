from __future__ import annotations

import hashlib
import asyncio
import json
import logging
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.procurement import (
    ProcurementLotObservation,
    ProcurementLotRecord,
    ProcurementSourceState,
    ProcurementSourceSyncRun,
    ProcurementSourceSyncState,
)
from app.schemas.procurements import ProcurementLotItem, ProcurementSourceInfo, ProcurementSyncResult
from app.services.procurement_classification import ProcurementClassification, classify_procurement_lot
from app.services.procurement_enrichment import classify_procurement_enrichment, schedule_procurement_lot_enrichment
from app.services.procurement_scoring import apply_procurement_score
from app.services.procurement_grid_state import bump_procurement_lot_dataset_version
from app.services.procurement_notifications import enqueue_procurement_telegram_notifications
from app.services.procurement_actuality import classify_procurement_actuality
from app.services.auction_analysis_config import auction_analysis_config_service, AnalysisRuntimeConfig
from app.services.procurement_sources import (
    get_procurement_source_provider,
    list_enabled_procurement_source_providers,
    ProcurementSourceProvider,
)
from app.services.procurement_values import parse_scraped_datetime
from app.services.source_http_diagnostics import (
    begin_source_http_diagnostics,
    collect_source_http_diagnostics,
    persist_procurement_source_http_diagnostics,
)
from app.services.zakupki_scraper import DEFAULT_SEARCH_KEYWORDS


logger = logging.getLogger(__name__)
settings = get_settings()
NEWNESS_WINDOW_DAYS = 3
CRITICAL_FIELDS = ("registry_number", "title", "initial_price_value", "application_deadline_at", "notice_url")
_MISSING = object()


@dataclass(slots=True)
class PreparedProcurementLot:
    item: ProcurementLotItem
    classification: ProcurementClassification
    normalized_item: dict
    content_hash: str


async def sync_zakupki_procurements(session: AsyncSession, *, limit: int | None = 100) -> ProcurementSyncResult:
    return await sync_procurement_source(session, source="zakupki", limit=limit)


async def sync_enabled_procurement_sources(session: AsyncSession, *, limit: int | None = 100) -> list[ProcurementSyncResult]:
    results: list[ProcurementSyncResult] = []
    for provider in list_enabled_procurement_source_providers():
        results.append(await sync_procurement_source_provider(session, provider=provider, limit=limit))
    return results


async def sync_procurement_source(
    session: AsyncSession,
    *,
    source: str,
    limit: int | None = 100,
) -> ProcurementSyncResult:
    provider = get_procurement_source_provider(source)
    if not provider.info().enabled:
        raise ValueError(f"Procurement source '{source}' is disabled")
    return await sync_procurement_source_provider(session, provider=provider, limit=limit)


async def sync_procurement_source_provider(
    session: AsyncSession,
    *,
    provider: ProcurementSourceProvider,
    limit: int | None = 100,
) -> ProcurementSyncResult:
    info = provider.info()
    if not info.enabled:
        raise ValueError(f"Procurement source '{info.code}' is disabled")
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
    missing_critical_fields: Counter[str] = Counter()
    parser_failure_count = 0
    parser_version = getattr(provider, "parser_version", None)
    await _upsert_source_sync_state(
        session,
        info.code,
        last_sync_started_at=now,
        last_sync_result="running",
        last_sync_error=None,
        last_sync_error_code=None,
        parser_version=parser_version,
    )
    await session.flush()
    sync_state = await session.get(ProcurementSourceSyncState, info.code)
    cursor = _normalize_sync_cursor(sync_state.cursor_payload if sync_state is not None else None)
    keywords = _provider_search_keywords(provider)
    keyword_index = _keyword_index(keywords, cursor.get("keyword"))
    page = _cursor_page(cursor)
    page_batch_size = max(1, int(settings.procurement_sync_page_batch_size or 1))
    max_pages_per_keyword = max(0, int(settings.procurement_sync_max_pages_per_keyword or 0))
    remaining_limit = limit if limit is not None and limit > 0 else None
    logger.info(
        "Procurement sync started: source=%s url=%s enabled=%s parser=%s limit=%s keyword=%s page=%s page_batch_size=%s",
        info.code,
        info.website,
        info.enabled,
        parser_version,
        limit,
        keywords[keyword_index] if keywords else None,
        page,
        page_batch_size,
    )

    diagnostics_token = begin_source_http_diagnostics()
    runtime_config = await auction_analysis_config_service.get_runtime_config(session, source="procurement")
    try:
        pages_processed = 0
        while pages_processed < page_batch_size and (remaining_limit is None or remaining_limit > 0):
            keyword = keywords[keyword_index]
            page_limit = remaining_limit if remaining_limit is not None else None
            items = await asyncio.to_thread(lambda: provider.list_lots_page(keyword=keyword, page=page, limit=page_limit))
            logger.info(
                "Procurement sync page fetched: source=%s keyword=%s page=%s items=%s",
                info.code,
                keyword,
                page,
                len(items),
            )
            if not items:
                keyword_index, page = _advance_procurement_cursor(
                    keyword_index=keyword_index,
                    page=page,
                    keywords=keywords,
                    exhausted=True,
                )
                await _store_procurement_cursor(session, info.code, keyword=keywords[keyword_index], page=page, exhausted=False)
                await persist_procurement_source_http_diagnostics(session, collect_source_http_diagnostics(diagnostics_token))
                diagnostics_token = begin_source_http_diagnostics()
                await session.commit()
                pages_processed += 1
                if max_pages_per_keyword > 0 and page > max_pages_per_keyword:
                    page = 1
                continue

            await _sync_procurement_items(
                session,
                info=info,
                items=items,
                result=result,
                missing_critical_fields=missing_critical_fields,
                observed_at=now,
                runtime_config=runtime_config,
            )
            pages_processed += 1
            if remaining_limit is not None:
                remaining_limit = max(0, remaining_limit - len(items))
            page += 1
            if max_pages_per_keyword > 0 and page > max_pages_per_keyword:
                keyword_index, page = _advance_procurement_cursor(
                    keyword_index=keyword_index,
                    page=page,
                    keywords=keywords,
                    exhausted=True,
                )
            await _store_procurement_cursor(session, info.code, keyword=keywords[keyword_index], page=page, exhausted=False)
            await persist_procurement_source_http_diagnostics(session, collect_source_http_diagnostics(diagnostics_token))
            diagnostics_token = begin_source_http_diagnostics()
            await session.commit()
    except Exception as error:
        diagnostics_events = collect_source_http_diagnostics(diagnostics_token)
        completed_at = datetime.now(UTC)
        parser_failure_count = max(parser_failure_count, 1)
        await session.rollback()
        await _ensure_source_state(session, info, completed_at=completed_at)
        await _upsert_source_sync_state(
            session,
            info.code,
            last_sync_started_at=now,
            last_sync_completed_at=completed_at,
            last_sync_result="failed",
            last_sync_error=str(error)[:2000],
            last_sync_error_code=type(error).__name__,
            last_sync_fetched=result.fetched,
            last_sync_created=result.created,
            last_sync_updated=result.updated,
            last_sync_unchanged=result.unchanged,
            last_sync_status_changed=result.status_changed,
            last_sync_parser_failures=parser_failure_count,
            last_sync_missing_critical_fields=dict(missing_critical_fields),
            parser_version=parser_version,
        )
        await _append_source_sync_run(
            session,
            source_code=info.code,
            started_at=now,
            completed_at=completed_at,
            result="failed",
            sync_result=result,
            parser_failure_count=parser_failure_count,
            missing_critical_fields=dict(missing_critical_fields),
            parser_version=parser_version,
            error_code=type(error).__name__,
            error_message=str(error)[:2000],
        )
        await persist_procurement_source_http_diagnostics(session, diagnostics_events)
        await session.commit()
        logger.exception("Procurement sync failed: source=%s url=%s parser=%s", info.code, info.website, parser_version)
        raise

    await persist_procurement_source_http_diagnostics(session, collect_source_http_diagnostics(diagnostics_token))
    completed_at = datetime.now(UTC)
    source_state.last_synced_at = completed_at
    await _upsert_source_sync_state(
        session,
        info.code,
        last_sync_completed_at=completed_at,
        last_successful_sync_at=completed_at,
        last_sync_result="success",
        last_sync_error=None,
        last_sync_error_code=None,
        last_sync_fetched=result.fetched,
        last_sync_created=result.created,
        last_sync_updated=result.updated,
        last_sync_unchanged=result.unchanged,
        last_sync_status_changed=result.status_changed,
        last_sync_parser_failures=parser_failure_count,
        last_sync_missing_critical_fields=dict(missing_critical_fields),
        parser_version=parser_version,
    )
    await _append_source_sync_run(
        session,
        source_code=info.code,
        started_at=now,
        completed_at=completed_at,
        result="success",
        sync_result=result,
        parser_failure_count=parser_failure_count,
        missing_critical_fields=dict(missing_critical_fields),
        parser_version=parser_version,
    )
    await session.commit()
    logger.info(
        "Procurement sync finished: source=%s url=%s status=success parser=%s fetched=%s created=%s updated=%s unchanged=%s missing=%s",
        info.code,
        info.website,
        parser_version,
        result.fetched,
        result.created,
        result.updated,
        result.unchanged,
        dict(missing_critical_fields),
    )
    return result


def prepare_procurement_lot(
    item: ProcurementLotItem,
    *,
    runtime_config: AnalysisRuntimeConfig | None = None,
) -> PreparedProcurementLot:
    classification = classify_procurement_lot(
        item,
        category_keywords=runtime_config.category_keywords if runtime_config is not None else None,
        exclusion_keywords=runtime_config.exclusion_keywords if runtime_config is not None else None,
    )
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


async def _sync_procurement_items(
    session: AsyncSession,
    *,
    info: ProcurementSourceInfo,
    items: list[ProcurementLotItem],
    result: ProcurementSyncResult,
    missing_critical_fields: Counter[str],
    observed_at: datetime,
    runtime_config: AnalysisRuntimeConfig,
) -> None:
    for item in items:
        result.fetched += 1
        prepared = prepare_procurement_lot(item, runtime_config=runtime_config)
        record = await _find_record(session, source_code=info.code, external_id=item.external_id)
        publication_at = parse_scraped_datetime(item.publication_date)
        deadline_at = parse_scraped_datetime(item.application_deadline)
        is_new = _is_new(publication_at=publication_at, observed_at=observed_at)
        _record_missing_critical_fields(item, deadline_at, missing_critical_fields)

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
                first_seen_at=observed_at,
                last_seen_at=observed_at,
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
            apply_procurement_score(record, current_time=observed_at)
            schedule_procurement_lot_enrichment(
                record,
                classify_procurement_enrichment(record),
                requested_at=observed_at,
                force=True,
            )
            _sync_procurement_record_actuality(record, checked_at=observed_at)
            session.add(record)
            await session.flush()
            await _add_procurement_observation(session, record)
            await bump_procurement_lot_dataset_version(
                session,
                record,
                event_type="row_inserted",
                payload={"source": "procurement_sync", "source_code": info.code},
            )
            if _is_active_lifecycle(record.lifecycle_status):
                await enqueue_procurement_telegram_notifications(session, record, now=observed_at)
            result.created += 1
            continue

        previous_lifecycle_status = _normalize_lifecycle_status(record.lifecycle_status)
        status_changed = record.status != item.status
        content_changed = record.content_hash != prepared.content_hash
        record.last_seen_at = observed_at
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
        record.is_new = _is_new(publication_at=publication_at or record.first_seen_at, observed_at=observed_at)
        record.category = prepared.classification.category
        record.matched_keywords = prepared.classification.matched_keywords
        record.excluded_keywords = prepared.classification.excluded_keywords
        record.filter_reason = prepared.classification.filter_reason
        record.normalized_item = prepared.normalized_item
        record.raw_item = item.model_dump(mode="json")
        apply_procurement_score(record, current_time=observed_at)
        schedule_procurement_lot_enrichment(
            record,
            classify_procurement_enrichment(record),
            requested_at=observed_at,
            force=content_changed,
        )
        next_lifecycle_status = _sync_procurement_record_actuality(record, checked_at=observed_at)
        lifecycle_changed = previous_lifecycle_status != next_lifecycle_status
        if status_changed:
            record.status_changed_at = observed_at
            result.status_changed += 1
        if content_changed:
            record.content_hash = prepared.content_hash
            result.updated += 1
            await _add_procurement_observation(session, record)
        else:
            result.unchanged += 1

        event_type = _procurement_lifecycle_event_type(previous_lifecycle_status, next_lifecycle_status)
        if event_type is None and content_changed:
            event_type = "row_updated"
        if event_type is not None:
            await bump_procurement_lot_dataset_version(
                session,
                record,
                event_type=event_type,
                payload={
                    "source": "procurement_sync",
                    "source_code": info.code,
                    "status_changed": status_changed,
                    "lifecycle_changed": lifecycle_changed,
                    "lifecycle_status": next_lifecycle_status,
                },
            )
        if _is_active_lifecycle(record.lifecycle_status):
            await enqueue_procurement_telegram_notifications(session, record, now=observed_at)


def _provider_search_keywords(provider: ProcurementSourceProvider) -> tuple[str, ...]:
    del provider
    return tuple(dict.fromkeys(keyword.strip() for keyword in DEFAULT_SEARCH_KEYWORDS if keyword.strip()))


def _sync_procurement_record_actuality(record: ProcurementLotRecord, *, checked_at: datetime) -> str:
    actuality = classify_procurement_actuality(record, current_time=checked_at)
    record.lifecycle_status = actuality.lifecycle_status
    record.finished_at = actuality.finished_at
    record.actuality_checked_at = checked_at
    if actuality.lifecycle_status == "active":
        record.archived_at = None
        record.archive_reason = None
    else:
        record.archived_at = checked_at
        record.archive_reason = actuality.archive_reason
        _clear_procurement_enrichment_state(record)
    return _normalize_lifecycle_status(actuality.lifecycle_status)


def _procurement_lifecycle_event_type(previous_status: str, next_status: str) -> str | None:
    if previous_status == next_status:
        return None
    if previous_status != "active" and next_status == "active":
        return "row_inserted"
    if previous_status == "active" and next_status != "active":
        return "row_deleted"
    return "row_updated"


def _normalize_lifecycle_status(value: object) -> str:
    return str(value or "active").strip().lower() or "active"


def _is_active_lifecycle(value: object) -> bool:
    return _normalize_lifecycle_status(value) == "active"


def _clear_procurement_enrichment_state(record: ProcurementLotRecord) -> None:
    record.enrichment_requested_at = None
    record.enrichment_requested_reason = None
    record.last_enrichment_attempt_at = None
    record.enrichment_attempt_count = 0
    record.next_enrichment_attempt_at = None
    record.last_enrichment_error = None
    record.enrichment_claimed_at = None
    record.enrichment_claimed_by = None
    record.enrichment_claim_expires_at = None


def _normalize_sync_cursor(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def _keyword_index(keywords: tuple[str, ...], keyword: object) -> int:
    if isinstance(keyword, str) and keyword in keywords:
        return keywords.index(keyword)
    return 0


def _cursor_page(cursor: dict[str, object]) -> int:
    page = cursor.get("page")
    try:
        return max(1, int(page))
    except (TypeError, ValueError):
        return 1


def _advance_procurement_cursor(
    *,
    keyword_index: int,
    page: int,
    keywords: tuple[str, ...],
    exhausted: bool,
) -> tuple[int, int]:
    if not exhausted:
        return keyword_index, max(1, page)
    next_keyword_index = keyword_index + 1
    if next_keyword_index >= len(keywords):
        next_keyword_index = 0
    return next_keyword_index, 1


async def _store_procurement_cursor(
    session: AsyncSession,
    source_code: str,
    *,
    keyword: str,
    page: int,
    exhausted: bool,
) -> None:
    sync_state = await session.get(ProcurementSourceSyncState, source_code)
    if sync_state is None:
        sync_state = ProcurementSourceSyncState(source_code=source_code, last_sync_missing_critical_fields={})
        session.add(sync_state)
    sync_state.cursor_payload = {
        "keyword": keyword,
        "page": max(1, int(page)),
        "exhausted": exhausted,
    }
    sync_state.cursor_updated_at = datetime.now(UTC)


async def _add_procurement_observation(session: AsyncSession, record: ProcurementLotRecord) -> None:
    session.add(
        ProcurementLotObservation(
            procurement_lot_record_id=int(record.id),
            content_hash=record.content_hash,
            status=record.status,
            normalized_item=record.normalized_item,
            raw_item=record.raw_item,
        )
    )


async def _ensure_source_state(
    session: AsyncSession,
    info: ProcurementSourceInfo,
    *,
    completed_at: datetime | None = None,
) -> ProcurementSourceState:
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
    if completed_at is not None:
        source_state.last_synced_at = completed_at
    return source_state


async def _upsert_source_sync_state(
    session: AsyncSession,
    source_code: str,
    *,
    last_sync_started_at: datetime | None | object = _MISSING,
    last_sync_completed_at: datetime | None | object = _MISSING,
    last_successful_sync_at: datetime | None | object = _MISSING,
    last_sync_result: str | None | object = _MISSING,
    last_sync_error: str | None | object = _MISSING,
    last_sync_error_code: str | None | object = _MISSING,
    last_sync_fetched: int | None | object = _MISSING,
    last_sync_created: int | None | object = _MISSING,
    last_sync_updated: int | None | object = _MISSING,
    last_sync_unchanged: int | None | object = _MISSING,
    last_sync_status_changed: int | None | object = _MISSING,
    last_sync_parser_failures: int | None | object = _MISSING,
    last_sync_missing_critical_fields: dict | object = _MISSING,
    parser_version: str | None | object = _MISSING,
) -> None:
    sync_state = await session.get(ProcurementSourceSyncState, source_code)
    if sync_state is None:
        sync_state = ProcurementSourceSyncState(source_code=source_code, last_sync_missing_critical_fields={})
        session.add(sync_state)

    if last_sync_started_at is not _MISSING:
        sync_state.last_sync_started_at = last_sync_started_at
    if last_sync_completed_at is not _MISSING:
        sync_state.last_sync_completed_at = last_sync_completed_at
    if last_successful_sync_at is not _MISSING:
        sync_state.last_successful_sync_at = last_successful_sync_at
    if last_sync_result is not _MISSING:
        sync_state.last_sync_result = last_sync_result
    if last_sync_error is not _MISSING:
        sync_state.last_sync_error = last_sync_error
    if last_sync_error_code is not _MISSING:
        sync_state.last_sync_error_code = last_sync_error_code
    if last_sync_fetched is not _MISSING:
        sync_state.last_sync_fetched = last_sync_fetched
    if last_sync_created is not _MISSING:
        sync_state.last_sync_created = last_sync_created
    if last_sync_updated is not _MISSING:
        sync_state.last_sync_updated = last_sync_updated
    if last_sync_unchanged is not _MISSING:
        sync_state.last_sync_unchanged = last_sync_unchanged
    if last_sync_status_changed is not _MISSING:
        sync_state.last_sync_status_changed = last_sync_status_changed
    if last_sync_parser_failures is not _MISSING:
        sync_state.last_sync_parser_failures = last_sync_parser_failures
    if last_sync_missing_critical_fields is not _MISSING:
        sync_state.last_sync_missing_critical_fields = dict(last_sync_missing_critical_fields or {})
    if parser_version is not _MISSING:
        sync_state.parser_version = parser_version


async def _append_source_sync_run(
    session: AsyncSession,
    *,
    source_code: str,
    started_at: datetime,
    completed_at: datetime | None,
    result: str,
    sync_result: ProcurementSyncResult,
    parser_failure_count: int,
    missing_critical_fields: dict[str, int],
    parser_version: str | None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    session.add(
        ProcurementSourceSyncRun(
            source_code=source_code,
            started_at=started_at,
            completed_at=completed_at,
            result=result,
            fetched_count=sync_result.fetched,
            created_count=sync_result.created,
            updated_count=sync_result.updated,
            unchanged_count=sync_result.unchanged,
            status_changed_count=sync_result.status_changed,
            parser_failure_count=parser_failure_count,
            missing_critical_fields=dict(missing_critical_fields),
            parser_version=parser_version,
            error_code=error_code,
            error_message=error_message,
        )
    )


def _record_missing_critical_fields(
    item: ProcurementLotItem,
    application_deadline_at: datetime | None,
    counter: Counter[str],
) -> None:
    values = {
        "registry_number": item.registry_number,
        "title": item.title,
        "initial_price_value": item.initial_price_value,
        "application_deadline_at": application_deadline_at,
        "notice_url": item.notice_url,
    }
    for field_name in CRITICAL_FIELDS:
        value = values[field_name]
        if value is None or (isinstance(value, str) and not value.strip()):
            counter[field_name] += 1


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
