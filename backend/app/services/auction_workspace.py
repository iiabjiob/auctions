from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from datetime import UTC, datetime
from time import perf_counter
from urllib.error import HTTPError, URLError

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from app.models.auction import (
    AuctionLotDetailCache,
    AuctionLotDetailObservation,
    AuctionLotObservation,
    AuctionLotRecord,
    AuctionLotWorkItem,
)
from app.schemas.auctions import (
    AuctionDetailResponse,
    AuctionDocument,
    LotChangeSummary,
    LotDetailResponse,
    LotFieldChange,
    LotWorkspaceBatchCommitItem,
    LotWorkspaceBatchCommitResponse,
    LotWorkspaceBatchCommittedItem,
    LotWorkspaceBatchRejectedItem,
    LotWorkItemResponse,
    LotWorkItemUpdate,
    LotWorkspaceResponse,
)
from app.infrastructure.redis.streams import publish_auction_event
from app.services.auction_analysis_config import auction_analysis_config_service
from app.services.auction_datagrid_payload import validate_datagrid_row_payload
from app.services.auction_scoring import (
    calculate_lot_economy,
    is_media_document,
    recalculate_record_rating,
    sync_record_from_detail_cache,
)
from app.services.auction_sources import get_source_provider


logger = logging.getLogger(__name__)
WORKSPACE_DETAIL_RAW_FIELDS_LIMIT = 160
WORKSPACE_DETAIL_DOCUMENTS_LIMIT = 160
WORKSPACE_DETAIL_RAW_TABLES_LIMIT = 20
WORKSPACE_DETAIL_PRICE_SCHEDULE_LIMIT = 120
WORKSPACE_DETAIL_TEXT_LIMIT = 4000
WORKSPACE_CHANGE_VALUE_LIMIT = 1000


async def get_lot_workspace(
    session: AsyncSession,
    *,
    source: str,
    lot_id: str,
    auction_id: str | None = None,
    refresh: bool = False,
    include_detail: bool = True,
) -> LotWorkspaceResponse:
    started_at = perf_counter()
    record = await find_lot_record(
        session,
        source=source,
        lot_id=lot_id,
        auction_id=auction_id,
        include_normalized_item=refresh or include_detail,
    )
    if record is None:
        raise LookupError("Lot record was not found in persisted catalog")

    detail_started_at = perf_counter()
    detail_cache = (
        await ensure_lot_detail_cache(session, record, refresh=True, include_price_schedule=False)
        if refresh
        else await get_cached_lot_detail_cache(session, record) if include_detail else None
    )
    detail_cached_at = detail_cache.fetched_at if detail_cache else await get_cached_lot_detail_fetched_at(session, record)
    logger.info(
        "Lot workspace detail cache resolved",
        extra={
            "source_code": source,
            "lot_id": lot_id,
            "lot_record_id": record.id,
            "has_detail_cache": detail_cache is not None,
            "refresh": refresh,
            "include_detail": include_detail,
            "elapsed_ms": round((perf_counter() - detail_started_at) * 1000),
        },
    )
    work_item = await ensure_work_item(session, record)
    if refresh:
        runtime_config = await auction_analysis_config_service.get_runtime_config(session)
        recalculate_record_rating(
            record,
            detail_cache,
            work_item,
            category_keywords=runtime_config.category_keywords,
            exclusion_keywords=runtime_config.exclusion_keywords,
            legal_risk_rules=runtime_config.legal_risk_rules,
            owner_profile=runtime_config.owner_profile,
            dimension_weights=runtime_config.dimension_weights,
        )
    await session.commit()

    response = await build_workspace_response(
        session,
        record,
        detail_cache,
        work_item,
        include_change_fields=refresh,
        include_embedded_row_payload=include_detail or refresh,
        detail_cached_at=detail_cached_at,
    )
    logger.info(
        "Lot workspace response built",
        extra={
            "source_code": source,
            "lot_id": lot_id,
            "lot_record_id": record.id,
            "elapsed_ms": round((perf_counter() - started_at) * 1000),
        },
    )
    return response


async def refresh_lot_workspace_live(
    session: AsyncSession,
    *,
    source: str,
    lot_id: str,
    auction_id: str | None = None,
) -> LotWorkspaceResponse:
    record = await find_lot_record(session, source=source, lot_id=lot_id, auction_id=auction_id)
    if record is None:
        raise LookupError("Lot record was not found in persisted catalog")

    detail_cache = await ensure_lot_detail_cache(
        session,
        record,
        refresh=True,
        include_price_schedule=False,
        raise_on_fetch_error=True,
    )
    work_item = await ensure_work_item(session, record)
    runtime_config = await auction_analysis_config_service.get_runtime_config(session)
    recalculate_record_rating(
        record,
        detail_cache,
        work_item,
        category_keywords=runtime_config.category_keywords,
        exclusion_keywords=runtime_config.exclusion_keywords,
        legal_risk_rules=runtime_config.legal_risk_rules,
        owner_profile=runtime_config.owner_profile,
        dimension_weights=runtime_config.dimension_weights,
    )
    await session.commit()
    response = await build_workspace_response(
        session,
        record,
        detail_cache,
        work_item,
        include_change_fields=True,
        include_embedded_row_payload=True,
        detail_cached_at=detail_cache.fetched_at if detail_cache else None,
    )
    await publish_auction_event("lot.row_updated", {"row": response.row.model_dump(mode="json")})
    await publish_auction_event(
        "lot.detail_refresh_completed",
        {
            "source": source,
            "lot_id": lot_id,
            "auction_id": auction_id,
            "record_id": response.record_id,
            "detail_cached_at": response.detail_cached_at.isoformat() if response.detail_cached_at else None,
        },
    )
    return response


async def update_lot_work_item(
    session: AsyncSession,
    *,
    source: str,
    lot_id: str,
    payload: LotWorkItemUpdate,
    auction_id: str | None = None,
) -> LotWorkspaceResponse:
    record = await find_lot_record(session, source=source, lot_id=lot_id, auction_id=auction_id)
    if record is None:
        raise LookupError("Lot record was not found in persisted catalog")

    detail_cache = await session.scalar(select(AuctionLotDetailCache).where(AuctionLotDetailCache.lot_record_id == record.id))
    if detail_cache is not None:
        sync_record_from_detail_cache(record, detail_cache)
    work_item = await ensure_work_item(session, record)
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        if field == "analogs":
            value = [dict(analog) for analog in value]
        setattr(work_item, field, value)

    runtime_config = await auction_analysis_config_service.get_runtime_config(session)
    recalculate_record_rating(
        record,
        detail_cache,
        work_item,
        category_keywords=runtime_config.category_keywords,
        exclusion_keywords=runtime_config.exclusion_keywords,
        legal_risk_rules=runtime_config.legal_risk_rules,
        owner_profile=runtime_config.owner_profile,
        dimension_weights=runtime_config.dimension_weights,
    )
    await session.commit()
    await session.refresh(work_item)
    await _publish_row_updated(record)
    return await build_workspace_response(session, record, detail_cache, work_item)


async def batch_update_lot_work_items(
    session: AsyncSession,
    *,
    updates: list[LotWorkspaceBatchCommitItem],
) -> LotWorkspaceBatchCommitResponse:
    committed: list[LotWorkspaceBatchCommittedItem] = []
    rejected: list[LotWorkspaceBatchRejectedItem] = []

    for item in updates:
        try:
            workspace = await update_lot_work_item(
                session,
                source=item.source,
                lot_id=item.lot_id,
                auction_id=item.auction_id,
                payload=item.payload,
            )
        except (LookupError, ValueError) as error:
            await session.rollback()
            rejected.append(
                LotWorkspaceBatchRejectedItem(
                    source=item.source,
                    lot_id=item.lot_id,
                    auction_id=item.auction_id,
                    error=str(error),
                )
            )
            continue
        except Exception as error:
            await session.rollback()
            logger.exception(
                "Batch lot workspace update failed",
                extra={
                    "source_code": item.source,
                    "lot_id": item.lot_id,
                    "auction_id": item.auction_id,
                },
            )
            rejected.append(
                LotWorkspaceBatchRejectedItem(
                    source=item.source,
                    lot_id=item.lot_id,
                    auction_id=item.auction_id,
                    error=str(error) or "Unexpected workspace update error",
                )
            )
            continue

        committed.append(
            LotWorkspaceBatchCommittedItem(
                source=item.source,
                lot_id=item.lot_id,
                auction_id=item.auction_id,
                workspace=workspace,
            )
        )

    return LotWorkspaceBatchCommitResponse(committed=committed, rejected=rejected)


async def find_lot_record(
    session: AsyncSession,
    *,
    source: str,
    lot_id: str,
    auction_id: str | None = None,
    include_normalized_item: bool = True,
) -> AuctionLotRecord | None:
    statement = select(AuctionLotRecord).where(
        AuctionLotRecord.source_code == source,
        AuctionLotRecord.lot_external_id == lot_id,
    )
    if auction_id:
        statement = statement.where(AuctionLotRecord.auction_external_id == auction_id)
    if not include_normalized_item:
        statement = statement.options(defer(AuctionLotRecord.normalized_item))
    statement = statement.order_by(AuctionLotRecord.last_seen_at.desc()).limit(1)
    return await session.scalar(statement)


async def ensure_lot_detail_cache(
    session: AsyncSession,
    record: AuctionLotRecord,
    *,
    refresh: bool = False,
    include_price_schedule: bool = True,
    raise_on_fetch_error: bool = False,
) -> AuctionLotDetailCache | None:
    statement = select(AuctionLotDetailCache).where(AuctionLotDetailCache.lot_record_id == record.id)
    detail_cache = await session.scalar(statement)
    if detail_cache is not None and not refresh and (not include_price_schedule or _detail_cache_has_price_schedule(detail_cache)):
        sync_record_from_detail_cache(record, detail_cache)
        return detail_cache

    provider = get_source_provider(record.source_code)
    try:
        lot_detail = await asyncio.to_thread(
            provider.get_lot,
            record.lot_external_id,
            include_price_schedule=include_price_schedule,
        )
    except NotImplementedError:
        return detail_cache
    except (HTTPError, URLError, TimeoutError, OSError) as error:
        if raise_on_fetch_error:
            raise
        logger.warning(
            "Failed to fetch lot detail from source; using cached detail when available",
            extra={
                "source_code": record.source_code,
                "lot_record_id": record.id,
                "lot_external_id": record.lot_external_id,
                "error": str(error),
            },
        )
        return detail_cache
    auction_detail = None
    if record.auction_external_id:
        try:
            auction_detail = await asyncio.to_thread(provider.get_auction, record.auction_external_id)
        except NotImplementedError:
            auction_detail = None
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            logger.warning(
                "Failed to fetch auction detail from source; continuing with lot detail only",
                extra={
                    "source_code": record.source_code,
                    "lot_record_id": record.id,
                    "auction_external_id": record.auction_external_id,
                    "error": str(error),
                },
            )
            auction_detail = None

    existing_schedule = _price_schedule_from_record_or_cache(record, detail_cache)
    lot_payload = _lot_detail_payload_with_price_schedule_state(
        lot_detail.model_dump(mode="json"),
        previous_payload=detail_cache.lot_detail if detail_cache else None,
        include_price_schedule=include_price_schedule,
        fallback_price_schedule=existing_schedule,
    )
    auction_payload = auction_detail.model_dump(mode="json") if auction_detail else None
    documents = _merge_documents(lot_detail, auction_detail)
    content_hash = hashlib.sha256(
        json.dumps(
            {
                "lot_detail": lot_payload,
                "auction_detail": auction_payload,
                "documents": documents,
            },
            sort_keys=True,
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()

    now = datetime.now(UTC)
    if detail_cache is None:
        detail_cache = AuctionLotDetailCache(
            lot_record_id=record.id,
            fetched_at=now,
            content_hash=content_hash,
            lot_detail=lot_payload,
            auction_detail=auction_payload,
            documents=documents,
        )
        session.add(detail_cache)
        await session.flush()
        sync_record_from_detail_cache(record, detail_cache)
        _add_detail_observation(session, record, detail_cache)
        return detail_cache

    content_changed = detail_cache.content_hash != content_hash
    detail_cache.fetched_at = now
    detail_cache.content_hash = content_hash
    detail_cache.lot_detail = lot_payload
    detail_cache.auction_detail = auction_payload
    detail_cache.documents = documents
    sync_record_from_detail_cache(record, detail_cache)
    if content_changed:
        _add_detail_observation(session, record, detail_cache)
    return detail_cache


async def get_cached_lot_detail_cache(
    session: AsyncSession,
    record: AuctionLotRecord,
) -> AuctionLotDetailCache | None:
    statement = select(AuctionLotDetailCache).where(AuctionLotDetailCache.lot_record_id == record.id)
    detail_cache = await session.scalar(statement)
    if detail_cache is not None:
        sync_record_from_detail_cache(record, detail_cache)
    return detail_cache


async def get_cached_lot_detail_fetched_at(
    session: AsyncSession,
    record: AuctionLotRecord,
) -> datetime | None:
    statement = select(AuctionLotDetailCache.fetched_at).where(AuctionLotDetailCache.lot_record_id == record.id)
    return await session.scalar(statement)


def _detail_cache_has_price_schedule(detail_cache: AuctionLotDetailCache) -> bool:
    payload = detail_cache.lot_detail or {}
    if payload.get("_price_schedule_loaded") is True:
        return True
    lot = payload.get("lot") or {}
    schedule = lot.get("price_schedule")
    return isinstance(schedule, list) and len(schedule) > 0


def _lot_detail_payload_with_price_schedule_state(
    payload: dict,
    *,
    previous_payload: dict | None,
    include_price_schedule: bool,
    fallback_price_schedule: list | None = None,
) -> dict:
    next_payload = dict(payload)
    lot = dict(next_payload.get("lot") or {})
    previous_lot = dict((previous_payload or {}).get("lot") or {})
    previous_schedule = previous_lot.get("price_schedule") or []
    current_schedule = lot.get("price_schedule") or []
    fallback_schedule = fallback_price_schedule or []

    if include_price_schedule:
        if not current_schedule and (previous_schedule or fallback_schedule):
            lot["price_schedule"] = previous_schedule or fallback_schedule
        next_payload["_price_schedule_loaded"] = True
    elif (previous_payload or {}).get("_price_schedule_loaded") is True or previous_schedule or fallback_schedule:
        lot["price_schedule"] = previous_schedule or fallback_schedule
        next_payload["_price_schedule_loaded"] = True
    else:
        next_payload["_price_schedule_loaded"] = False

    next_payload["lot"] = lot
    return next_payload


def _price_schedule_from_record_or_cache(
    record: AuctionLotRecord,
    detail_cache: AuctionLotDetailCache | None,
) -> list:
    row_schedule = (record.datagrid_row or {}).get("price_schedule")
    if isinstance(row_schedule, list) and row_schedule:
        return row_schedule
    normalized_lot = (record.normalized_item or {}).get("lot") or {}
    normalized_schedule = normalized_lot.get("price_schedule")
    if isinstance(normalized_schedule, list) and normalized_schedule:
        return normalized_schedule
    cache_lot = ((detail_cache.lot_detail or {}).get("lot") or {}) if detail_cache else {}
    cache_schedule = cache_lot.get("price_schedule")
    return cache_schedule if isinstance(cache_schedule, list) else []


def _add_detail_observation(
    session: AsyncSession,
    record: AuctionLotRecord,
    detail_cache: AuctionLotDetailCache,
) -> None:
    session.add(
        AuctionLotDetailObservation(
            lot_record_id=record.id,
            content_hash=detail_cache.content_hash,
            lot_detail=detail_cache.lot_detail,
            auction_detail=detail_cache.auction_detail,
            documents=detail_cache.documents,
        )
    )


async def ensure_work_item(session: AsyncSession, record: AuctionLotRecord) -> AuctionLotWorkItem:
    statement = select(AuctionLotWorkItem).where(AuctionLotWorkItem.lot_record_id == record.id)
    work_item = await session.scalar(statement)
    if work_item is not None:
        return work_item

    work_item = AuctionLotWorkItem(lot_record_id=record.id, analogs=[])
    session.add(work_item)
    await session.flush()
    return work_item


async def build_workspace_response(
    session: AsyncSession,
    record: AuctionLotRecord,
    detail_cache: AuctionLotDetailCache | None,
    work_item: AuctionLotWorkItem,
    *,
    include_change_fields: bool = False,
    include_embedded_row_payload: bool = True,
    detail_cached_at: datetime | None = None,
) -> LotWorkspaceResponse:
    lot_detail = _lot_detail_response_from_cache(record, detail_cache)
    auction_detail = (
        AuctionDetailResponse.model_validate(detail_cache.auction_detail)
        if detail_cache and detail_cache.auction_detail
        else None
    )
    row = validate_datagrid_row_payload(_workspace_row_payload(record, include_embedded_payload=include_embedded_row_payload))
    row.work_decision_status = work_item.decision_status
    return LotWorkspaceResponse(
        record_id=record.id,
        row=row,
        lot_detail=lot_detail,
        auction_detail=auction_detail,
        detail_cached_at=detail_cached_at if detail_cached_at is not None else detail_cache.fetched_at if detail_cache else None,
        work_item=_work_item_response(work_item),
        economy=calculate_lot_economy(record, work_item),
        changes=await _change_summary(session, record, include_fields=include_change_fields),
    )


def _workspace_row_payload(record: AuctionLotRecord, *, include_embedded_payload: bool) -> dict:
    payload = dict(record.datagrid_row or {})
    if include_embedded_payload:
        return payload

    payload["price_schedule"] = []
    payload["images"] = []
    payload["primary_image_url"] = None
    payload["image_count"] = 0
    return payload


def _lot_detail_response_from_cache(
    record: AuctionLotRecord,
    detail_cache: AuctionLotDetailCache | None,
) -> LotDetailResponse | None:
    if detail_cache is None:
        return None

    payload = _bounded_detail_payload(dict(detail_cache.lot_detail or {}))
    lot = dict(payload.get("lot") or {})
    if not lot.get("price_schedule"):
        fallback_schedule = _price_schedule_from_record_or_cache(record, detail_cache)
        if fallback_schedule:
            lot["price_schedule"] = fallback_schedule
            payload["lot"] = lot
    return LotDetailResponse.model_validate(payload)


def _bounded_detail_payload(payload: dict) -> dict:
    bounded = dict(payload)
    lot = dict(bounded.get("lot") or {})
    lot["price_schedule"] = _bounded_list(lot.get("price_schedule"), WORKSPACE_DETAIL_PRICE_SCHEDULE_LIMIT)
    for key, value in list(lot.items()):
        if isinstance(value, str):
            lot[key] = _truncate_text(value, WORKSPACE_DETAIL_TEXT_LIMIT)
    bounded["lot"] = lot
    bounded["documents"] = _bounded_list(bounded.get("documents"), WORKSPACE_DETAIL_DOCUMENTS_LIMIT)
    bounded["raw_fields"] = [
        {
            **field,
            "value": _truncate_text(str(field.get("value") or ""), WORKSPACE_DETAIL_TEXT_LIMIT),
        }
        for field in _bounded_list(bounded.get("raw_fields"), WORKSPACE_DETAIL_RAW_FIELDS_LIMIT)
        if isinstance(field, dict)
    ]
    bounded["raw_tables"] = _bounded_list(bounded.get("raw_tables"), WORKSPACE_DETAIL_RAW_TABLES_LIMIT)
    return bounded


def _bounded_list(value: object, limit: int) -> list:
    return list(value[:limit]) if isinstance(value, list) else []


def _truncate_text(value: str | None, limit: int) -> str | None:
    if value is None or len(value) <= limit:
        return value
    return f"{value[:limit].rstrip()}..."


async def _publish_row_updated(record: AuctionLotRecord) -> None:
    row = validate_datagrid_row_payload(record.datagrid_row)
    await publish_auction_event("lot.row_updated", {"row": row.model_dump(mode="json")})


def _work_item_response(work_item: AuctionLotWorkItem) -> LotWorkItemResponse:
    return LotWorkItemResponse(
        id=work_item.id,
        lot_record_id=work_item.lot_record_id,
        decision_status=work_item.decision_status,
        assignee=work_item.assignee,
        comment=work_item.comment,
        inspection_at=work_item.inspection_at,
        inspection_result=work_item.inspection_result,
        final_decision=work_item.final_decision,
        investor=work_item.investor,
        deposit_status=work_item.deposit_status,
        application_status=work_item.application_status,
        exclude_from_analysis=work_item.exclude_from_analysis,
        exclusion_reason=work_item.exclusion_reason,
        category_override=work_item.category_override,
        max_purchase_price=work_item.max_purchase_price,
        market_value=work_item.market_value,
        platform_fee=work_item.platform_fee,
        delivery_cost=work_item.delivery_cost,
        dismantling_cost=work_item.dismantling_cost,
        repair_cost=work_item.repair_cost,
        storage_cost=work_item.storage_cost,
        legal_cost=work_item.legal_cost,
        other_costs=work_item.other_costs,
        target_profit=work_item.target_profit,
        analogs=work_item.analogs or [],
        created_at=work_item.created_at,
        updated_at=work_item.updated_at,
    )


async def _change_summary(session: AsyncSession, record: AuctionLotRecord, *, include_fields: bool = False) -> LotChangeSummary:
    count_statement = select(func.count(AuctionLotObservation.id)).where(AuctionLotObservation.lot_record_id == record.id)
    observations_count = await session.scalar(count_statement) or 0
    detail_count_statement = select(func.count(AuctionLotDetailObservation.id)).where(
        AuctionLotDetailObservation.lot_record_id == record.id
    )
    detail_observations_count = await session.scalar(detail_count_statement) or 0
    observation_timestamps_statement = (
        select(AuctionLotObservation.observed_at)
        .where(AuctionLotObservation.lot_record_id == record.id)
        .order_by(AuctionLotObservation.observed_at.desc())
        .limit(2)
    )
    observation_timestamps = list((await session.scalars(observation_timestamps_statement)).all())
    detail_observation_timestamps_statement = (
        select(AuctionLotDetailObservation.observed_at)
        .where(AuctionLotDetailObservation.lot_record_id == record.id)
        .order_by(AuctionLotDetailObservation.observed_at.desc())
        .limit(2)
    )
    detail_observation_timestamps = list((await session.scalars(detail_observation_timestamps_statement)).all())
    field_changes: list[LotFieldChange] = []
    if include_fields:
        observation_statement = (
            select(AuctionLotObservation)
            .where(AuctionLotObservation.lot_record_id == record.id)
            .order_by(AuctionLotObservation.observed_at.desc())
            .limit(2)
        )
        observations = list((await session.scalars(observation_statement)).all())
        detail_observation_statement = (
            select(AuctionLotDetailObservation)
            .where(AuctionLotDetailObservation.lot_record_id == record.id)
            .order_by(AuctionLotDetailObservation.observed_at.desc())
            .limit(2)
        )
        detail_observations = list((await session.scalars(detail_observation_statement)).all())
        field_changes = _list_observation_changes(observations)
        field_changes.extend(_detail_observation_changes(detail_observations))

    return LotChangeSummary(
        observations_count=observations_count,
        detail_observations_count=detail_observations_count,
        last_observed_at=observation_timestamps[0] if observation_timestamps else None,
        previous_observed_at=observation_timestamps[1] if len(observation_timestamps) > 1 else None,
        last_detail_observed_at=detail_observation_timestamps[0] if detail_observation_timestamps else None,
        previous_detail_observed_at=detail_observation_timestamps[1] if len(detail_observation_timestamps) > 1 else None,
        status_changed_at=record.status_changed_at,
        content_changed=observations_count > 1,
        detail_changed=detail_observations_count > 1,
        fields=field_changes,
    )


def _list_observation_changes(observations: list[AuctionLotObservation]) -> list[LotFieldChange]:
    if len(observations) < 2:
        return []

    current = observations[0].normalized_item or {}
    previous = observations[1].normalized_item or {}
    checks = [
        ("Статус", ("lot", "status"), "status"),
        ("Цена", ("lot", "initial_price"), "price"),
        ("Название лота", ("lot", "name"), "description"),
        ("Окончание заявок", ("auction", "application_deadline"), "date"),
        ("Дата торгов", ("auction", "auction_date"), "date"),
        ("Организатор", ("organizer", "name"), "organizer"),
    ]
    changes: list[LotFieldChange] = []
    for label, path, change_type in checks:
        before = _deep_get(previous, path)
        after = _deep_get(current, path)
        if _clean_value(before) != _clean_value(after):
            changes.append(
                LotFieldChange(
                    label=label,
                    previous=_clean_value(before),
                    current=_clean_value(after),
                    change_type=change_type,
                )
            )
    return changes


def _detail_observation_changes(observations: list[AuctionLotDetailObservation]) -> list[LotFieldChange]:
    if len(observations) < 2:
        return []

    current = observations[0]
    previous = observations[1]
    changes: list[LotFieldChange] = []
    current_documents = current.documents or []
    previous_documents = previous.documents or []
    if len(current_documents) != len(previous_documents):
        changes.append(
            LotFieldChange(
                label="Документы",
                previous=str(len(previous_documents)),
                current=str(len(current_documents)),
                change_type="documents",
            )
        )

    current_media = sum(1 for document in current_documents if is_media_document(document))
    previous_media = sum(1 for document in previous_documents if is_media_document(document))
    if current_media != previous_media:
        changes.append(
            LotFieldChange(
                label="Фото/медиа",
                previous=str(previous_media),
                current=str(current_media),
                change_type="documents",
            )
        )

    detail_checks = [
        ("Описание имущества", ("lot", "description"), "description"),
        ("Порядок осмотра", ("lot", "inspection_order"), "description"),
        ("Задаток", ("lot", "deposit_amount"), "price"),
        ("Порядок внесения задатка", ("lot", "deposit_order"), "description"),
        ("ИНН должника", ("debtor", "inn"), "debtor"),
        ("Телефон организатора", ("organizer", "phone"), "organizer"),
    ]
    current_payload = _combined_detail_payload(current)
    previous_payload = _combined_detail_payload(previous)
    for label, path, change_type in detail_checks:
        before = _deep_get(previous_payload, path)
        after = _deep_get(current_payload, path)
        if _clean_value(before) != _clean_value(after):
            changes.append(
                LotFieldChange(
                    label=label,
                    previous=_clean_value(before),
                    current=_clean_value(after),
                    change_type=change_type,
                )
            )
    return changes


def _combined_detail_payload(observation: AuctionLotDetailObservation) -> dict:
    lot_detail = observation.lot_detail or {}
    auction_detail = observation.auction_detail or {}
    return {
        "lot": lot_detail.get("lot") or {},
        "auction": auction_detail.get("auction") or lot_detail.get("auction") or {},
        "organizer": auction_detail.get("organizer") or {},
        "debtor": auction_detail.get("debtor") or {},
    }


def _deep_get(payload: dict, path: tuple[str, ...]) -> object:
    current: object = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _clean_value(value: object) -> str | None:
    if value is None:
        return None
    normalized = re.sub(r"\s+", " ", str(value)).strip()
    return _truncate_text(normalized, WORKSPACE_CHANGE_VALUE_LIMIT) or None


def _merge_documents(lot_detail: LotDetailResponse, auction_detail: AuctionDetailResponse | None) -> list[dict]:
    seen: set[str] = set()
    documents: list[dict] = []
    for document in [*lot_detail.documents, *(auction_detail.documents if auction_detail else [])]:
        payload = document.model_dump(mode="json") if isinstance(document, AuctionDocument) else dict(document)
        key = payload.get("external_id") or payload.get("url") or payload.get("name")
        if not key or key in seen:
            continue
        seen.add(key)
        documents.append(payload)
    return documents
