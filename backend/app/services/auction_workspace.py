from __future__ import annotations

import asyncio
import hashlib
import json
import re
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

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
    LotDatagridRow,
    LotDetailResponse,
    LotEconomyResponse,
    LotFieldChange,
    LotRating,
    LotWorkItemResponse,
    LotWorkItemUpdate,
    LotWorkspaceResponse,
)
from app.infrastructure.redis.streams import publish_auction_event
from app.services.auction_analysis import LegalRiskRules, build_lot_analysis
from app.services.auction_analysis_config import auction_analysis_config_service
from app.services.auction_catalog import parse_price
from app.services.auction_sources import get_source_provider


async def get_lot_workspace(
    session: AsyncSession,
    *,
    source: str,
    lot_id: str,
    auction_id: str | None = None,
    refresh: bool = False,
) -> LotWorkspaceResponse:
    record = await find_lot_record(session, source=source, lot_id=lot_id, auction_id=auction_id)
    if record is None:
        raise LookupError("Lot record was not found in persisted catalog")

    detail_cache = await ensure_lot_detail_cache(session, record, refresh=refresh)
    work_item = await ensure_work_item(session, record)
    runtime_config = await auction_analysis_config_service.get_runtime_config(session)
    recalculate_record_rating(
        record,
        detail_cache,
        work_item,
        category_keywords=runtime_config.category_keywords,
        exclusion_keywords=runtime_config.exclusion_keywords,
        legal_risk_rules=runtime_config.legal_risk_rules,
    )
    await session.commit()

    return await build_workspace_response(session, record, detail_cache, work_item)


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
        _sync_record_from_detail_cache(record, detail_cache)
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
    )
    await session.commit()
    await session.refresh(work_item)
    await _publish_row_updated(record)
    return await build_workspace_response(session, record, detail_cache, work_item)


async def find_lot_record(
    session: AsyncSession,
    *,
    source: str,
    lot_id: str,
    auction_id: str | None = None,
) -> AuctionLotRecord | None:
    statement = select(AuctionLotRecord).where(
        AuctionLotRecord.source_code == source,
        AuctionLotRecord.lot_external_id == lot_id,
    )
    if auction_id:
        statement = statement.where(AuctionLotRecord.auction_external_id == auction_id)
    statement = statement.order_by(AuctionLotRecord.last_seen_at.desc()).limit(1)
    return await session.scalar(statement)


async def ensure_lot_detail_cache(
    session: AsyncSession,
    record: AuctionLotRecord,
    *,
    refresh: bool = False,
) -> AuctionLotDetailCache | None:
    statement = select(AuctionLotDetailCache).where(AuctionLotDetailCache.lot_record_id == record.id)
    detail_cache = await session.scalar(statement)
    if detail_cache is not None and not refresh:
        _sync_record_from_detail_cache(record, detail_cache)
        return detail_cache

    provider = get_source_provider(record.source_code)
    try:
        lot_detail = await asyncio.to_thread(provider.get_lot, record.lot_external_id)
    except NotImplementedError:
        return detail_cache
    auction_detail = None
    if record.auction_external_id:
        try:
            auction_detail = await asyncio.to_thread(provider.get_auction, record.auction_external_id)
        except NotImplementedError:
            auction_detail = None

    lot_payload = lot_detail.model_dump(mode="json")
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
        _sync_record_from_detail_cache(record, detail_cache)
        _add_detail_observation(session, record, detail_cache)
        return detail_cache

    content_changed = detail_cache.content_hash != content_hash
    detail_cache.fetched_at = now
    detail_cache.content_hash = content_hash
    detail_cache.lot_detail = lot_payload
    detail_cache.auction_detail = auction_payload
    detail_cache.documents = documents
    _sync_record_from_detail_cache(record, detail_cache)
    if content_changed:
        _add_detail_observation(session, record, detail_cache)
    return detail_cache


def _sync_record_from_detail_cache(record: AuctionLotRecord, detail_cache: AuctionLotDetailCache) -> None:
    publication_date = _publication_date_from_detail_cache(detail_cache)
    lot_details = _lot_details_from_detail_cache(detail_cache)
    auction_details = _auction_details_from_detail_cache(detail_cache)

    row = dict(record.datagrid_row or {})
    if publication_date and row.get("publication_date") != publication_date:
        row["publication_date"] = publication_date
    for key, value in auction_details.items():
        if value is not None:
            row[key] = value
    for key, value in lot_details.items():
        if value is not None:
            row[key] = value
    if lot_details.get("initial_price"):
        row["initial_price_value"] = str(parse_price(lot_details["initial_price"])) if parse_price(lot_details["initial_price"]) is not None else None
    current_price = lot_details.get("current_price") or row.get("current_price") or record.initial_price
    if current_price:
        current_price_value = parse_price(current_price)
        row["current_price"] = current_price
        row["current_price_value"] = str(current_price_value) if current_price_value is not None else None
        record.initial_price = current_price
    minimum_price = lot_details.get("minimum_price") or row.get("minimum_price")
    if minimum_price:
        minimum_price_value = parse_price(minimum_price)
        row["minimum_price"] = minimum_price
        row["minimum_price_value"] = str(minimum_price_value) if minimum_price_value is not None else None
    record.datagrid_row = row

    normalized_item = dict(record.normalized_item or {})
    auction_payload = dict(normalized_item.get("auction") or {})
    if publication_date and auction_payload.get("publication_date") != publication_date:
        auction_payload["publication_date"] = publication_date
    for key, value in auction_details.items():
        if value is not None:
            auction_payload[key] = value
    if auction_payload:
        normalized_item["auction"] = auction_payload
    lot_payload = dict(normalized_item.get("lot") or {})
    for key, value in lot_details.items():
        if value is not None:
            lot_payload[key] = value
    if lot_payload:
        normalized_item["lot"] = lot_payload
    record.normalized_item = normalized_item


def _publication_date_from_detail_cache(detail_cache: AuctionLotDetailCache | None) -> str | None:
    if detail_cache is None:
        return None
    for payload in (detail_cache.auction_detail or {}, detail_cache.lot_detail or {}):
        auction = payload.get("auction") or {}
        publication_date = auction.get("publication_date")
        if isinstance(publication_date, str) and publication_date.strip():
            return publication_date.strip()
    return None


def _lot_details_from_detail_cache(detail_cache: AuctionLotDetailCache | None) -> dict[str, str | None]:
    if detail_cache is None:
        return {}
    payload = detail_cache.lot_detail or {}
    lot = payload.get("lot") or {}
    return {
        "category": _clean_text(lot.get("category")) or _raw_field_value(payload.get("raw_fields") or [], "Категория площадки", "Категория"),
        "location": _clean_text(lot.get("location")),
        "location_region": _clean_text(lot.get("region")),
        "location_city": _clean_text(lot.get("city")),
        "location_address": _clean_text(lot.get("address")),
        "location_coordinates": _clean_text(lot.get("coordinates")),
        "initial_price": _clean_text(lot.get("initial_price")),
        "current_price": _clean_text(lot.get("current_price")),
        "minimum_price": _clean_text(lot.get("minimum_price")),
    }


def _auction_details_from_detail_cache(detail_cache: AuctionLotDetailCache | None) -> dict[str, str | None]:
    details = {
        "application_start": None,
        "application_deadline": None,
        "auction_date": None,
    }
    if detail_cache is None:
        return details

    for payload in (detail_cache.auction_detail or {}, detail_cache.lot_detail or {}):
        auction = payload.get("auction") or {}
        for key in details:
            details[key] = details[key] or _clean_datetime_text(auction.get(key))

        raw_fields = payload.get("raw_fields") or []
        application_start, application_deadline = _raw_datetime_range(raw_fields, "Прием заявок", "Приём заявок")
        auction_start, _auction_deadline = _raw_datetime_range(raw_fields, "Проведение торгов")
        details["application_start"] = details["application_start"] or application_start
        details["application_deadline"] = details["application_deadline"] or application_deadline
        details["auction_date"] = details["auction_date"] or auction_start

    return details


def _clean_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _clean_datetime_text(value: object) -> str | None:
    cleaned = _clean_text(value)
    if not cleaned:
        return None
    return re.sub(
        r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b",
        lambda match: f"{int(match.group(1)):02d}.{int(match.group(2)):02d}.{match.group(3)}",
        cleaned,
    )


def _raw_field_value(fields: list[dict], *names: str) -> str | None:
    wanted = {name.lower().rstrip(":") for name in names}
    for field in fields:
        field_name = str(field.get("name") or "").lower().rstrip(":")
        value = field.get("value")
        if field_name in wanted and isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _raw_datetime_range(fields: list[dict], *names: str) -> tuple[str | None, str | None]:
    value = _raw_field_value(fields, *names)
    if not value:
        return None, None
    match = re.search(r"\bс\s+(.+?)\s+до\s+(.+)$", value, re.IGNORECASE)
    if not match:
        return None, _clean_datetime_text(value)
    return _clean_datetime_text(match.group(1)), _clean_datetime_text(match.group(2))


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
) -> LotWorkspaceResponse:
    lot_detail = LotDetailResponse.model_validate(detail_cache.lot_detail) if detail_cache else None
    auction_detail = (
        AuctionDetailResponse.model_validate(detail_cache.auction_detail)
        if detail_cache and detail_cache.auction_detail
        else None
    )
    row = LotDatagridRow.model_validate(record.datagrid_row)
    row.work_decision_status = work_item.decision_status
    return LotWorkspaceResponse(
        record_id=record.id,
        row=row,
        lot_detail=lot_detail,
        auction_detail=auction_detail,
        detail_cached_at=detail_cache.fetched_at if detail_cache else None,
        work_item=_work_item_response(work_item),
        economy=_calculate_economy(record, work_item),
        changes=await _change_summary(session, record),
    )


def recalculate_record_rating(
    record: AuctionLotRecord,
    detail_cache: AuctionLotDetailCache | None,
    work_item: AuctionLotWorkItem | None = None,
    *,
    category_keywords: dict[str, tuple[str, ...]] | None = None,
    exclusion_keywords: tuple[str, ...] | None = None,
    legal_risk_rules: LegalRiskRules | None = None,
) -> LotRating:
    if detail_cache is not None:
        _sync_record_from_detail_cache(record, detail_cache)
    row = LotDatagridRow.model_validate(record.datagrid_row)
    economy = _calculate_economy(record, work_item) if work_item else LotEconomyResponse(current_price=parse_price(record.initial_price))
    row.analysis = build_lot_analysis(
        record,
        row,
        detail_cache,
        work_item,
        economy,
        category_keywords=category_keywords,
        exclusion_keywords=exclusion_keywords,
        legal_risk_rules=legal_risk_rules,
    )
    row.model_category = row.analysis.category or row.model_category
    row.category = row.category or row.model_category
    row.market_value = work_item.market_value if work_item and work_item.market_value is not None else row.market_value
    row.platform_fee = work_item.platform_fee if work_item else None
    row.delivery_cost = work_item.delivery_cost if work_item else None
    row.dismantling_cost = work_item.dismantling_cost if work_item else None
    row.repair_cost = work_item.repair_cost if work_item else None
    row.storage_cost = work_item.storage_cost if work_item else None
    row.legal_cost = work_item.legal_cost if work_item else None
    row.other_costs = work_item.other_costs if work_item else None
    row.target_profit = work_item.target_profit if work_item else None
    row.total_expenses = economy.total_expenses
    row.full_entry_cost = economy.full_entry_cost
    row.potential_profit = economy.potential_profit
    row.roi = economy.roi
    row.market_discount = economy.market_discount if economy.market_discount is not None else row.market_discount
    row.formula_max_purchase_price = economy.max_purchase_price
    row.exclude_from_analysis = work_item.exclude_from_analysis if work_item else False
    row.exclusion_reason = work_item.exclusion_reason if work_item else None
    rating = _calculate_workspace_rating(record, row, detail_cache, work_item, economy)
    row.rating = rating
    row.work_decision_status = work_item.decision_status if work_item else None
    record.rating_score = rating.score
    record.rating_level = rating.level
    record.datagrid_row = row.model_dump(mode="json")
    return rating


async def _publish_row_updated(record: AuctionLotRecord) -> None:
    row = LotDatagridRow.model_validate(record.datagrid_row)
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


def _calculate_economy(record: AuctionLotRecord, work_item: AuctionLotWorkItem) -> LotEconomyResponse:
    current_price = parse_price(record.initial_price)
    expense_fields = [
        work_item.platform_fee,
        work_item.delivery_cost,
        work_item.dismantling_cost,
        work_item.repair_cost,
        work_item.storage_cost,
        work_item.legal_cost,
        work_item.other_costs,
    ]
    expenses = sum((value or Decimal("0") for value in expense_fields), Decimal("0"))
    full_entry_cost = current_price + expenses if current_price is not None else None
    potential_profit = (
        work_item.market_value - full_entry_cost
        if work_item.market_value is not None and full_entry_cost is not None
        else None
    )
    roi = potential_profit / full_entry_cost if potential_profit is not None and full_entry_cost else None
    market_discount = (
        Decimal("1") - (current_price / work_item.market_value)
        if current_price is not None and work_item.market_value
        else None
    )
    max_purchase_price = (
        work_item.market_value - expenses - (work_item.target_profit or Decimal("0"))
        if work_item.market_value is not None
        else None
    )

    return LotEconomyResponse(
        current_price=current_price,
        market_value=work_item.market_value,
        total_expenses=expenses,
        full_entry_cost=full_entry_cost,
        potential_profit=potential_profit,
        roi=roi,
        market_discount=market_discount,
        target_profit=work_item.target_profit,
        max_purchase_price=max_purchase_price,
    )


def _calculate_workspace_rating(
    record: AuctionLotRecord,
    row: LotDatagridRow,
    detail_cache: AuctionLotDetailCache | None,
    work_item: AuctionLotWorkItem | None,
    economy: LotEconomyResponse,
) -> LotRating:
    score = 35
    reasons = ["Базовая оценка по статусу, данным площадки и ручной экономике"]
    status = (record.status or row.status or "").lower()

    if "приём" in status or "прием" in status:
        score += 20
        reasons.append("Идет прием заявок")
    if "публич" in status:
        score += 12
        reasons.append("Публичное предложение")
    if "отмен" in status:
        score -= 50
        reasons.append("Лот отменен")
    if economy.current_price is not None:
        score += 8
        reasons.append("Цена распознана")

    deadline = _parse_deadline(row.application_deadline)
    if deadline:
        score += 4
        remaining_hours = (deadline - datetime.now()).total_seconds() / 3600
        if 0 <= remaining_hours <= 48:
            score += 10
            reasons.append("До окончания заявок меньше 48 часов")

    documents = detail_cache.documents if detail_cache else []
    if documents:
        score += 6
        reasons.append("Есть документы")
    elif detail_cache:
        score -= 10
        reasons.append("Документы не найдены")

    media_documents = [document for document in documents if _is_media_document(document)]
    if media_documents:
        score += 6
        reasons.append("Есть фото или фотоархив")
    elif detail_cache:
        score -= 5
        reasons.append("Фото не найдены")

    if detail_cache:
        lot_detail = detail_cache.lot_detail or {}
        lot = lot_detail.get("lot") or {}
        if lot.get("inspection_order"):
            score += 4
            reasons.append("Есть порядок осмотра")
        if lot.get("description"):
            score += 3
            reasons.append("Есть подробное описание")

    if economy.market_discount is not None:
        if economy.market_discount >= Decimal("0.50"):
            score += 25
            reasons.append("Дисконт к рынку 50%+")
        elif economy.market_discount >= Decimal("0.30"):
            score += 18
            reasons.append("Дисконт к рынку 30%+")
        elif economy.market_discount >= Decimal("0.15"):
            score += 10
            reasons.append("Есть дисконт к рынку")

    if economy.roi is not None:
        if economy.roi >= Decimal("0.50"):
            score += 20
            reasons.append("ROI 50%+")
        elif economy.roi >= Decimal("0.25"):
            score += 12
            reasons.append("ROI 25%+")
        elif economy.roi > 0:
            score += 6
            reasons.append("Положительный ROI")

    if economy.potential_profit is not None and economy.potential_profit > 0:
        score += 5
        reasons.append("Потенциальная прибыль положительная")

    decision = (work_item.decision_status or "") if work_item else ""
    if decision == "reject":
        score -= 60
        reasons.append("Команда отметила отказ")
    elif decision in {"inspection", "bid"}:
        score += 8
        reasons.append("Лот взят в работу")
    elif decision in {"watch", "calculate"}:
        score += 4
        reasons.append("Лот отмечен для проверки")

    score = max(0, min(100, score))
    if score >= 70:
        level = "high"
    elif score >= 45:
        level = "medium"
    else:
        level = "low"
    return LotRating(score=score, level=level, reasons=reasons)


def _is_media_document(document: dict) -> bool:
    text = " ".join(str(document.get(key) or "") for key in ["name", "document_type", "comment", "url"]).lower()
    return bool(re.search(r"фото|photo|изображ|\.rar|\.zip|\.7z|\.jpe?g|\.png|\.webp", text))


def _parse_deadline(value: str | None) -> datetime | None:
    if not value:
        return None
    for pattern in (
        "%d.%m.%Y %H:%M:%S",
        "%d.%m.%Y %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(value[:19], pattern)
        except ValueError:
            continue
    return None


async def _change_summary(session: AsyncSession, record: AuctionLotRecord) -> LotChangeSummary:
    count_statement = select(func.count(AuctionLotObservation.id)).where(AuctionLotObservation.lot_record_id == record.id)
    observations_count = await session.scalar(count_statement) or 0
    detail_count_statement = select(func.count(AuctionLotDetailObservation.id)).where(
        AuctionLotDetailObservation.lot_record_id == record.id
    )
    detail_observations_count = await session.scalar(detail_count_statement) or 0
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
        last_observed_at=observations[0].observed_at if observations else None,
        previous_observed_at=observations[1].observed_at if len(observations) > 1 else None,
        last_detail_observed_at=detail_observations[0].observed_at if detail_observations else None,
        previous_detail_observed_at=detail_observations[1].observed_at if len(detail_observations) > 1 else None,
        status_changed_at=record.status_changed_at,
        content_changed=len(observations) > 1,
        detail_changed=len(detail_observations) > 1,
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

    current_media = sum(1 for document in current_documents if _is_media_document(document))
    previous_media = sum(1 for document in previous_documents if _is_media_document(document))
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
    return normalized or None


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
