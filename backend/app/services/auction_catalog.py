from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, DecimalException
from typing import Any

from sqlalchemy import Integer, Numeric, String, and_, case, cast, func, not_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auction import AuctionLotDetailCache, AuctionLotRecord, AuctionLotWorkItem
from app.schemas.auctions import (
    AuctionListItem,
    DatagridColumn,
    LotDatagridFilters,
    LotDatagridHistogramEntry,
    LotDatagridPagination,
    LotDatagridResponse,
    LotDatagridRow,
    LotFreshness,
)
from app.schemas.auction_grid import AuctionLotsGridSummary
from app.services.auction_datagrid_payload import validate_datagrid_row_payload
from app.services.auction_grid_state import auction_lot_grid_row_id
from app.services.auction_scoring import calculate_list_lot_rating
from app.services.auction_sources import SOURCE_PROVIDERS, list_source_infos
from app.services.auction_values import parse_price


LOT_GRID_COLUMNS = [
    DatagridColumn(key="rating.score", title="Рейтинг", data_type="number", width=96),
    DatagridColumn(key="freshness.is_new", title="Новый", data_type="boolean", width=84),
    DatagridColumn(key="source_title", title="Площадка", width=120),
    DatagridColumn(key="auction_number", title="Аукцион", width=120),
    DatagridColumn(key="publication_date", title="Дата публикации", data_type="datetime", width=160),
    DatagridColumn(key="lot_number", title="Лот", width=80),
    DatagridColumn(key="lot_name", title="Наименование", width=420),
    DatagridColumn(key="category", title="Категория", width=180),
    DatagridColumn(key="debtor_name", title="Должник", width=220),
    DatagridColumn(key="location", title="Локация", width=220),
    DatagridColumn(key="initial_price_value", title="Начальная цена", data_type="money", width=150),
    DatagridColumn(key="current_price_value", title="Текущая цена", data_type="money", width=150),
    DatagridColumn(key="minimum_price_value", title="Мин. цена", data_type="money", width=150),
    DatagridColumn(key="status", title="Статус", width=160),
    DatagridColumn(key="organizer_name", title="Организатор", width=220),
    DatagridColumn(key="application_deadline", title="Прием заявок до", data_type="datetime", width=180),
    DatagridColumn(key="auction_date", title="Дата торгов", data_type="datetime", width=180),
]

SHORTLIST_DECISIONS = {"watch", "calculate", "inspection", "bid"}
SHORTLIST_MIN_SCORE = 85
LOT_DATASET_MAX_ROWS = 10_000
MIN_TEXT_SEARCH_LENGTH = 3
DEFAULT_QUICK_FILTER_COLUMNS = (
    "lotName",
    "location",
    "organizer",
    "auctionNumber",
    "lotNumber",
    "status",
    "sourceTitle",
    "analysisLabel",
    "analysisCategory",
    "exclusionReason",
)
GRID_COLUMN_ALIASES = {
    "analysis.category": "analysisCategory",
    "analysis.color": "analysisColor",
    "analysis.label": "analysisLabel",
    "analysis.status": "analysisStatus",
    "analysis_category": "analysisCategory",
    "analysis_color": "analysisColor",
    "analysis_label": "analysisLabel",
    "analysis_status": "analysisStatus",
    "application_deadline": "applicationDeadline",
    "auction_date": "auctionDate",
    "auction_id": "auctionId",
    "auction_name": "auctionName",
    "auction_number": "auctionNumber",
    "auction_url": "auctionUrl",
    "currentPrice": "price",
    "currentPriceValue": "price",
    "current_price_value": "price",
    "debtor_name": "debtorName",
    "delivery_cost": "deliveryCost",
    "dismantling_cost": "dismantlingCost",
    "exclude_from_analysis": "excludeFromAnalysis",
    "exclusion_reason": "exclusionReason",
    "first_seen_at": "firstSeenAt",
    "formula_max_purchase_price": "formulaMaxPurchasePrice",
    "freshness.first_seen_at": "firstSeenAt",
    "freshness.is_new": "isNew",
    "freshness.last_seen_at": "lastSeenAt",
    "full_entry_cost": "fullEntryCost",
    "image_count": "imageCount",
    "initial_price_value": "initialPrice",
    "is_new": "isNew",
    "last_seen_at": "lastSeenAt",
    "legal_cost": "legalCost",
    "location_address": "locationAddress",
    "location_city": "locationCity",
    "location_coordinates": "locationCoordinates",
    "location_region": "locationRegion",
    "lot_description": "lotDescription",
    "lot_id": "lotId",
    "lot_name": "lotName",
    "lot_number": "lotNumber",
    "lot_url": "lotUrl",
    "market_discount": "marketDiscount",
    "market_value": "marketValue",
    "minimum_price_value": "minimumPrice",
    "model_category": "modelCategory",
    "organizerName": "organizer",
    "organizer_name": "organizer",
    "other_costs": "otherCosts",
    "platform_fee": "platformFee",
    "potential_profit": "potentialProfit",
    "primary_image_url": "primaryImageUrl",
    "publication_date": "publicationDate",
    "rating.level": "ratingLevel",
    "rating.score": "ratingScore",
    "rating_level": "ratingLevel",
    "rating_score": "ratingScore",
    "repair_cost": "repairCost",
    "roi": "roiValue",
    "roi_value": "roiValue",
    "row_id": "id",
    "source_position": "sourcePosition",
    "source_title": "sourceTitle",
    "storage_cost": "storageCost",
    "target_profit": "targetProfit",
    "total_expenses": "totalExpenses",
    "work_decision_status": "workDecisionStatus",
}
LOT_PERIOD_DAYS = {
    "week": 7,
    "month": 31,
    "year": 365,
}


def list_lots_for_datagrid(
    *,
    period: str = "month",
    source: str | None = None,
    status: str | None = None,
    analysis_color: str | None = None,
    min_price: Decimal | None = None,
    max_price: Decimal | None = None,
    only_new: bool = False,
    shortlist: bool = False,
    min_rating: int | None = None,
    page: int = 1,
    page_size: int = 100,
) -> LotDatagridResponse:
    filters = LotDatagridFilters(
        period=period,
        source=source,
        status=status,
        analysis_color=analysis_color,
        min_price=min_price,
        max_price=max_price,
        only_new=only_new,
        shortlist=shortlist,
        min_rating=min_rating,
    )
    providers = _select_providers(source)
    source_titles = {provider.code: provider.title for provider in providers}
    source_scan_limit = min(max(page * page_size * 5, page_size), 1000)
    matched_rows: list[LotDatagridRow] = []

    for provider in providers:
        for item in provider.list_lots(limit=source_scan_limit):
            row = build_datagrid_row(item, source_titles.get(item.source, item.source))
            if filters.shortlist and row.rating.score < SHORTLIST_MIN_SCORE:
                continue
            if _matches_filters(row, filters):
                matched_rows.append(row)

    paged_rows, pagination = paginate_rows(matched_rows, page=page, page_size=page_size)

    return LotDatagridResponse(
        columns=LOT_GRID_COLUMNS,
        rows=paged_rows,
        filters=filters,
        total=pagination.total,
        pagination=pagination,
        available_sources=list_source_infos(),
    )


async def list_persisted_lots_for_datagrid(
    session: AsyncSession,
    *,
    period: str = "month",
    source: str | None = None,
    status: str | None = None,
    analysis_color: str | None = None,
    min_price: Decimal | None = None,
    max_price: Decimal | None = None,
    only_new: bool = False,
    shortlist: bool = False,
    min_rating: int | None = None,
    include_archived: bool = False,
    page: int = 1,
    page_size: int = 100,
    offset: int | None = None,
    sort_by: str | None = None,
    sort_direction: str = "asc",
    sort_model: list[dict] | None = None,
    grid_filter: dict | None = None,
) -> LotDatagridResponse:
    safe_page_size = min(page_size, LOT_DATASET_MAX_ROWS)
    filters = LotDatagridFilters(
        period=period,
        source=source,
        status=status,
        analysis_color=analysis_color,
        min_price=min_price,
        max_price=max_price,
        only_new=only_new,
        shortlist=shortlist,
        min_rating=min_rating,
        include_archived=include_archived,
    )
    active_sources = tuple(SOURCE_PROVIDERS)
    if source and source != "all" and source not in SOURCE_PROVIDERS:
        supported = ", ".join(sorted(SOURCE_PROVIDERS))
        raise ValueError(f"Unsupported auction source '{source}'. Supported: {supported}")
    statement = _build_persisted_lots_statement(filters, active_sources, grid_filter=grid_filter)
    total = await _count_persisted_lots(session, statement)
    pagination = _pagination_from_total(total, page=page, page_size=safe_page_size, offset=offset)
    resolved_offset = max(0, offset) if offset is not None else (pagination.page - 1) * safe_page_size
    statement = _apply_record_sort(statement, sort_by=sort_by, sort_direction=sort_direction, sort_model=sort_model)
    statement = statement.offset(resolved_offset).limit(safe_page_size)
    records = (await session.scalars(statement)).all()
    work_items = await _work_items_by_record_id(session, [record.id for record in records])
    detail_caches = await _detail_caches_by_record_id(session, [record.id for record in records])
    rows: list[LotDatagridRow] = []
    for record in records:
        row = validate_datagrid_row_payload(record.datagrid_row)
        row.row_id = auction_lot_grid_row_id(record)
        _hydrate_row_from_normalized_item(row, record.normalized_item)
        _hydrate_row_from_detail_cache(row, detail_caches.get(record.id))
        row.model_category = row.model_category or row.analysis.category
        _apply_display_category(row)
        work_item = work_items.get(record.id)
        _attach_work_item_state(row, work_item)
        rows.append(row)

    return LotDatagridResponse(
        columns=LOT_GRID_COLUMNS,
        rows=rows,
        filters=filters,
        total=total,
        pagination=pagination,
        available_sources=list_source_infos(),
    )


async def pull_persisted_lots_for_grid(
    session: AsyncSession,
    *,
    start_row: int,
    end_row: int,
    period: str = "month",
    source: str | None = None,
    status: str | None = None,
    analysis_color: str | None = None,
    min_price: Decimal | None = None,
    max_price: Decimal | None = None,
    only_new: bool = False,
    shortlist: bool = False,
    min_rating: int | None = None,
    include_archived: bool = False,
    sort_model: list[dict] | None = None,
    grid_filter: dict | None = None,
) -> tuple[list[tuple[AuctionLotRecord, LotDatagridRow]], int]:
    resolved_start = max(0, start_row)
    resolved_end = max(resolved_start, end_row)
    limit = min(resolved_end - resolved_start, LOT_DATASET_MAX_ROWS)
    filters = LotDatagridFilters(
        period=period,
        source=source,
        status=status,
        analysis_color=analysis_color,
        min_price=min_price,
        max_price=max_price,
        only_new=only_new,
        shortlist=shortlist,
        min_rating=min_rating,
        include_archived=include_archived,
    )
    active_sources = tuple(SOURCE_PROVIDERS)
    if source and source != "all" and source not in SOURCE_PROVIDERS:
        supported = ", ".join(sorted(SOURCE_PROVIDERS))
        raise ValueError(f"Unsupported auction source '{source}'. Supported: {supported}")

    statement = _build_persisted_lots_statement(filters, active_sources, grid_filter=grid_filter)
    total = await _count_persisted_lots(session, statement)
    if limit == 0:
        return [], total

    statement = _apply_record_sort(statement, sort_model=sort_model)
    records = (await session.scalars(statement.offset(resolved_start).limit(limit))).all()
    work_items = await _work_items_by_record_id(session, [record.id for record in records])
    detail_caches = await _detail_caches_by_record_id(session, [record.id for record in records])

    rows: list[tuple[AuctionLotRecord, LotDatagridRow]] = []
    for record in records:
        row = validate_datagrid_row_payload(record.datagrid_row)
        row.row_id = auction_lot_grid_row_id(record)
        _hydrate_row_from_normalized_item(row, record.normalized_item)
        _hydrate_row_from_detail_cache(row, detail_caches.get(record.id))
        row.model_category = row.model_category or row.analysis.category
        _apply_display_category(row)
        _attach_work_item_state(row, work_items.get(record.id))
        rows.append((record, row))
    return rows, total


async def summarize_persisted_lots_for_grid(
    session: AsyncSession,
    *,
    period: str = "month",
    source: str | None = None,
    status: str | None = None,
    analysis_color: str | None = None,
    min_price: Decimal | None = None,
    max_price: Decimal | None = None,
    only_new: bool = False,
    shortlist: bool = False,
    min_rating: int | None = None,
    include_archived: bool = False,
    grid_filter: dict | None = None,
) -> AuctionLotsGridSummary:
    filters = LotDatagridFilters(
        period=period,
        source=source,
        status=status,
        analysis_color=analysis_color,
        min_price=min_price,
        max_price=max_price,
        only_new=only_new,
        shortlist=shortlist,
        min_rating=min_rating,
        include_archived=include_archived,
    )
    active_sources = tuple(SOURCE_PROVIDERS)
    if source and source != "all" and source not in SOURCE_PROVIDERS:
        supported = ", ".join(sorted(SOURCE_PROVIDERS))
        raise ValueError(f"Unsupported auction source '{source}'. Supported: {supported}")

    statement = _build_persisted_lots_statement(filters, active_sources, grid_filter=grid_filter)
    base_query = (
        statement.with_only_columns(
            AuctionLotRecord.id.label("id"),
            AuctionLotRecord.is_new.label("is_new"),
            AuctionLotRecord.status.label("status"),
            AuctionLotRecord.rating_score.label("rating_score"),
        )
        .order_by(None)
        .subquery()
    )
    status_text = func.lower(func.coalesce(base_query.c.status, ""))
    open_applications = or_(
        status_text.like("%прием%"),
        status_text.like("%приём%"),
    )
    result = await session.execute(
        select(
            func.count(base_query.c.id),
            func.coalesce(func.sum(case((base_query.c.is_new.is_(True), 1), else_=0)), 0),
            func.coalesce(func.sum(case((open_applications, 1), else_=0)), 0),
            func.coalesce(func.sum(case((base_query.c.rating_score >= 75, 1), else_=0)), 0),
        )
    )
    total, new_count, open_applications_count, high_rating_count = result.one()
    return AuctionLotsGridSummary(
        total=int(total or 0),
        new_count=int(new_count or 0),
        open_applications_count=int(open_applications_count or 0),
        high_rating_count=int(high_rating_count or 0),
    )


async def list_persisted_lot_column_histogram(
    session: AsyncSession,
    *,
    period: str = "month",
    source: str | None = None,
    status: str | None = None,
    analysis_color: str | None = None,
    min_price: Decimal | None = None,
    max_price: Decimal | None = None,
    only_new: bool = False,
    shortlist: bool = False,
    min_rating: int | None = None,
    include_archived: bool = False,
    column_id: str,
    histogram_options: dict[str, Any] | None = None,
    sort_model: list[dict] | None = None,
    grid_filter: dict | None = None,
) -> list[LotDatagridHistogramEntry]:
    expression, value_type = _grid_column_expression(column_id)
    if expression is None:
        raise ValueError(f"Unsupported histogram column '{column_id}'")

    filters = LotDatagridFilters(
        period=period,
        source=source,
        status=status,
        analysis_color=analysis_color,
        min_price=min_price,
        max_price=max_price,
        only_new=only_new,
        shortlist=shortlist,
        min_rating=min_rating,
        include_archived=include_archived,
    )
    active_sources = tuple(SOURCE_PROVIDERS)
    if source and source != "all" and source not in SOURCE_PROVIDERS:
        supported = ", ".join(sorted(SOURCE_PROVIDERS))
        raise ValueError(f"Unsupported auction source '{source}'. Supported: {supported}")
    if _grid_filter_has_quick_filter(grid_filter):
        return []

    options = histogram_options or {}
    effective_grid_filter = None if options.get("scope") == "sourceAll" else grid_filter
    value_label = "histogram_value"
    base_statement = _build_persisted_lots_statement(filters, active_sources, grid_filter=effective_grid_filter)
    base_query = base_statement.with_only_columns(expression.label(value_label)).order_by(None).subquery()
    value_column = base_query.c[value_label]
    count_column = func.count().label("count")
    statement = select(value_column, count_column).select_from(base_query)

    search = str(options.get("search") or "").strip().lower()
    if search:
        statement = statement.where(func.lower(func.coalesce(cast(value_column, String), "")).like(f"%{_escape_like(search)}%", escape="\\"))

    statement = statement.group_by(value_column)
    if options.get("orderBy") == "valueAsc":
        statement = statement.order_by(cast(value_column, String).asc().nulls_first())
    else:
        statement = statement.order_by(count_column.desc(), cast(value_column, String).asc().nulls_first())

    result = await session.execute(statement.limit(_histogram_limit(options.get("limit"))))
    return [
        LotDatagridHistogramEntry(
            token=_serialize_histogram_token(value, value_type),
            value=_histogram_json_value(value),
            count=int(count or 0),
            text=_histogram_text_value(value),
        )
        for value, count in result.all()
    ]


def _build_persisted_lots_statement(
    filters: LotDatagridFilters,
    active_sources: tuple[str, ...],
    *,
    grid_filter: dict | None = None,
):
    statement = select(AuctionLotRecord).where(AuctionLotRecord.last_seen_at >= _period_cutoff(filters.period))
    if filters.source and filters.source != "all":
        statement = statement.where(AuctionLotRecord.source_code == filters.source)
    else:
        statement = statement.where(AuctionLotRecord.source_code.in_(active_sources))
    if not filters.include_archived:
        statement = statement.where(AuctionLotRecord.lifecycle_status == "active")
    if filters.status:
        statement = statement.where(AuctionLotRecord.status == filters.status)
    if filters.analysis_color:
        statement = statement.where(_json_nested_text_value("analysis", "color") == filters.analysis_color)
    if filters.only_new:
        statement = statement.where(AuctionLotRecord.is_new.is_(True))
    if filters.min_rating is not None:
        statement = statement.where(AuctionLotRecord.rating_score >= filters.min_rating)
    if filters.min_price is not None:
        statement = statement.where(_json_decimal_value("current_price_value") >= filters.min_price)
    if filters.max_price is not None:
        statement = statement.where(_json_decimal_value("current_price_value") <= filters.max_price)
    if filters.shortlist:
        statement = statement.where(_shortlist_record_predicate())
    grid_predicate = _grid_filter_predicate(grid_filter)
    if grid_predicate is not None:
        statement = statement.where(grid_predicate)
    return statement


async def _count_persisted_lots(session: AsyncSession, statement) -> int:
    return int(await session.scalar(select(func.count()).select_from(statement.order_by(None).subquery())) or 0)


def _apply_record_sort(
    statement,
    *,
    sort_by: str | None = None,
    sort_direction: str = "asc",
    sort_model: list[dict] | None = None,
):
    sort_entries = _normalize_sort_model(sort_by=sort_by, sort_direction=sort_direction, sort_model=sort_model)
    order_by = []
    for entry in sort_entries[:5]:
        expression = _sort_expression(entry["key"])
        if expression is None:
            continue
        ordered_expression = expression.desc() if entry["direction"] == "desc" else expression.asc()
        order_by.append(ordered_expression.nulls_last())

    if not order_by:
        return _apply_default_record_sort(statement)

    return statement.order_by(
        *order_by,
        AuctionLotRecord.source_code.asc(),
        AuctionLotRecord.auction_external_id.asc(),
        AuctionLotRecord.lot_external_id.asc(),
        AuctionLotRecord.id.asc(),
    )


def _normalize_sort_model(*, sort_by: str | None, sort_direction: str, sort_model: list[dict] | None) -> list[dict]:
    if sort_model:
        normalized = []
        for item in sort_model:
            key = item.get("key") if isinstance(item, dict) else None
            direction = item.get("direction") if isinstance(item, dict) else None
            if isinstance(key, str) and direction in {"asc", "desc"}:
                normalized.append({"key": key, "direction": direction})
        if normalized:
            return normalized
    if sort_by:
        return [{"key": sort_by, "direction": sort_direction if sort_direction in {"asc", "desc"} else "asc"}]
    return []


def _apply_default_record_sort(statement):
    return statement.order_by(
        AuctionLotRecord.source_code.asc(),
        AuctionLotRecord.first_seen_at.desc(),
        AuctionLotRecord.id.desc(),
    )


def _sort_expression(sort_by: str | None):
    expression = _grid_column_expression(sort_by)[0]
    if expression is not None:
        return expression
    normalized_sort_by = _normalize_grid_column_key(sort_by)
    return {
        "analysisCategory": _json_text_value("category"),
        "analysisColor": _json_nested_text_value("analysis", "color"),
        "analysisLabel": _json_nested_text_value("analysis", "label"),
        "applicationDeadline": _json_text_value("application_deadline"),
        "auctionDate": _json_text_value("auction_date"),
        "auctionNumber": AuctionLotRecord.auction_number,
        "category": _json_text_value("category"),
        "debtorName": _json_text_value("debtor_name"),
        "initialPrice": _json_decimal_value("initial_price_value"),
        "isNew": AuctionLotRecord.is_new,
        "location": _json_text_value("location"),
        "lotName": AuctionLotRecord.lot_name,
        "lotNumber": AuctionLotRecord.lot_number,
        "marketValue": _json_decimal_value("market_value"),
        "minimumPrice": _json_decimal_value("minimum_price_value"),
        "organizer": _json_text_value("organizer_name"),
        "price": _json_decimal_value("current_price_value"),
        "publicationDate": _json_text_value("publication_date"),
        "ratingScore": AuctionLotRecord.rating_score,
        "source": AuctionLotRecord.source_code,
        "sourcePosition": _json_integer_value("source_position"),
        "sourceTitle": func.coalesce(_json_text_value("source_title"), AuctionLotRecord.source_code),
        "status": AuctionLotRecord.status,
        "workDecisionStatus": _work_item_text_value("decision_status"),
    }.get(normalized_sort_by or "")


def _grid_column_expression(key: str | None):
    if not key:
        return None, "text"
    normalized_key = _normalize_grid_column_key(key)
    return {
        "analysisStatus": (_json_nested_text_value("analysis", "status"), "text"),
        "analysisCategory": (_json_text_value("category"), "text"),
        "analysisColor": (_json_nested_text_value("analysis", "color"), "text"),
        "analysisLabel": (_json_nested_text_value("analysis", "label"), "text"),
        "applicationDeadline": (_json_text_value("application_deadline"), "text"),
        "auctionDate": (_json_text_value("auction_date"), "text"),
        "auctionId": (_json_text_value("auction_id"), "text"),
        "auctionNumber": (AuctionLotRecord.auction_number, "text"),
        "auctionName": (_json_text_value("auction_name"), "text"),
        "auctionUrl": (_json_text_value("auction_url"), "text"),
        "category": (_json_text_value("category"), "text"),
        "debtorName": (_json_text_value("debtor_name"), "text"),
        "deliveryCost": (_json_decimal_value("delivery_cost"), "number"),
        "dismantlingCost": (_json_decimal_value("dismantling_cost"), "number"),
        "excludeFromAnalysis": (_json_boolean_value("exclude_from_analysis"), "boolean"),
        "exclusionReason": (_json_text_value("exclusion_reason"), "text"),
        "firstSeenAt": (AuctionLotRecord.first_seen_at, "datetime"),
        "formulaMaxPurchasePrice": (_json_decimal_value("formula_max_purchase_price"), "number"),
        "fullEntryCost": (_grid_full_entry_cost_value(), "number"),
        "id": (_json_text_value("row_id"), "text"),
        "imageCount": (_json_integer_value("image_count"), "number"),
        "initialPrice": (_json_decimal_value("initial_price_value"), "number"),
        "isNew": (AuctionLotRecord.is_new, "boolean"),
        "lastSeenAt": (AuctionLotRecord.last_seen_at, "datetime"),
        "legalCost": (_json_decimal_value("legal_cost"), "number"),
        "location": (_json_text_value("location"), "text"),
        "locationAddress": (_json_text_value("location_address"), "text"),
        "locationCity": (_json_text_value("location_city"), "text"),
        "locationCoordinates": (_json_text_value("location_coordinates"), "text"),
        "locationRegion": (_json_text_value("location_region"), "text"),
        "lotDescription": (_json_text_value("lot_description"), "text"),
        "lotId": (_json_text_value("lot_id"), "text"),
        "lotName": (AuctionLotRecord.lot_name, "text"),
        "lotNumber": (AuctionLotRecord.lot_number, "text"),
        "lotUrl": (_json_text_value("lot_url"), "text"),
        "marketDiscount": (_json_decimal_value("market_discount"), "number"),
        "marketValue": (_json_decimal_value("market_value"), "number"),
        "minimumPrice": (_json_decimal_value("minimum_price_value"), "number"),
        "modelCategory": (_json_text_value("model_category"), "text"),
        "organizer": (_json_text_value("organizer_name"), "text"),
        "otherCosts": (_json_decimal_value("other_costs"), "number"),
        "platformFee": (_json_decimal_value("platform_fee"), "number"),
        "potentialProfit": (_grid_potential_profit_value(), "number"),
        "price": (_json_decimal_value("current_price_value"), "number"),
        "primaryImageUrl": (_json_text_value("primary_image_url"), "text"),
        "publicationDate": (_json_text_value("publication_date"), "text"),
        "ratingLevel": (_json_nested_text_value("rating", "level"), "text"),
        "ratingScore": (AuctionLotRecord.rating_score, "number"),
        "repairCost": (_json_decimal_value("repair_cost"), "number"),
        "roiValue": (_grid_roi_value(), "number"),
        "source": (AuctionLotRecord.source_code, "text"),
        "sourcePosition": (_json_integer_value("source_position"), "number"),
        "sourceTitle": (func.coalesce(_json_text_value("source_title"), AuctionLotRecord.source_code), "text"),
        "status": (AuctionLotRecord.status, "text"),
        "storageCost": (_json_decimal_value("storage_cost"), "number"),
        "targetProfit": (_json_decimal_value("target_profit"), "number"),
        "totalExpenses": (_grid_total_expenses_value(), "number"),
        "workDecisionStatus": (_work_item_text_value("decision_status"), "text"),
    }.get(normalized_key, (None, "text"))


def _normalize_grid_column_key(key: str | None) -> str | None:
    if not key:
        return key
    return GRID_COLUMN_ALIASES.get(key, key)


def _grid_filter_predicate(grid_filter: dict | None):
    if not grid_filter:
        return None
    predicates = []
    column_filters = grid_filter.get("columnFilters")
    if isinstance(column_filters, dict):
        for key, payload in column_filters.items():
            predicate = _column_filter_predicate(str(key), payload)
            if predicate is not None:
                predicates.append(predicate)

    advanced_filters = grid_filter.get("advancedFilters")
    if isinstance(advanced_filters, dict):
        for key, payload in advanced_filters.items():
            predicate = _advanced_filter_predicate(str(key), payload)
            if predicate is not None:
                predicates.append(predicate)

    advanced_expression = grid_filter.get("advancedExpression")
    predicate = _advanced_expression_predicate(advanced_expression)
    if predicate is not None:
        predicates.append(predicate)

    quick_filter = grid_filter.get("quickFilter")
    predicate = _quick_filter_predicate(quick_filter)
    if predicate is not None:
        predicates.append(predicate)

    if not predicates:
        return None
    return and_(*predicates)


def _column_filter_predicate(key: str, payload):
    if not isinstance(payload, dict):
        return None
    kind = payload.get("kind")
    if kind == "valueSet":
        tokens = payload.get("tokens")
        if not isinstance(tokens, list) or not tokens:
            return None
        expression, _ = _grid_column_expression(key)
        if expression is None:
            return None
        return _value_set_tokens_predicate(expression, [str(token) for token in tokens])
    if kind == "predicate":
        return _predicate_filter_condition(key, payload.get("operator"), payload.get("value"), payload.get("value2"), payload.get("caseSensitive"))
    return None


def _advanced_filter_predicate(key: str, payload):
    if not isinstance(payload, dict):
        return None
    predicates = []
    for clause in payload.get("clauses") or []:
        if not isinstance(clause, dict):
            continue
        predicate = _predicate_filter_condition(key, clause.get("operator"), clause.get("value"), clause.get("value2"), False)
        if predicate is not None:
            predicates.append((clause.get("join") or "and", predicate))
    return _combine_joined_predicates(predicates)


def _advanced_expression_predicate(payload):
    if not isinstance(payload, dict):
        return None
    kind = payload.get("kind")
    if kind == "condition":
        return _predicate_filter_condition(payload.get("key"), payload.get("operator"), payload.get("value"), payload.get("value2"), False)
    if kind == "group":
        children = [_advanced_expression_predicate(child) for child in payload.get("children") or []]
        predicates = [predicate for predicate in children if predicate is not None]
        if not predicates:
            return None
        return or_(*predicates) if payload.get("operator") == "or" else and_(*predicates)
    if kind == "not":
        child = _advanced_expression_predicate(payload.get("child"))
        return not_(child) if child is not None else None
    return None


def _predicate_filter_condition(key, operator, value=None, value2=None, case_sensitive=False):
    operator = _normalize_filter_operator(operator)
    if key == "__shortlist":
        normalized_value = _coerce_filter_value(value, "boolean")
        return _shortlist_record_predicate() if operator == "equals" and normalized_value is True else None

    normalized_key = str(key) if key else None
    if operator in {"contains", "startsWith", "endsWith"}:
        expression, _ = _grid_column_expression(normalized_key)
        if expression is None or not _is_search_text_allowed(value):
            return None
        pattern_value = _escape_like(str(value))
        text_expression = cast(expression, String)
        compared_text = text_expression if case_sensitive else func.lower(text_expression)
        compared_value = pattern_value if case_sensitive else pattern_value.lower()
        if operator == "contains":
            return compared_text.like(f"%{compared_value}%", escape="\\")
        if operator == "startsWith":
            return compared_text.like(f"{compared_value}%", escape="\\")
        return compared_text.like(f"%{compared_value}", escape="\\")

    expression, value_type = _grid_column_expression(normalized_key)
    if expression is None or not isinstance(operator, str):
        return None

    text_expression = cast(expression, String)
    comparable_expression = expression if value_type in {"number", "boolean", "datetime"} else text_expression
    normalized_value = _coerce_filter_value(value, value_type)
    normalized_value2 = _coerce_filter_value(value2, value_type)

    if operator == "isNull":
        return expression.is_(None)
    if operator == "notNull":
        return expression.is_not(None)
    if operator == "isEmpty":
        return or_(expression.is_(None), text_expression == "")
    if operator == "notEmpty":
        return and_(expression.is_not(None), text_expression != "")
    if operator == "between":
        if normalized_value is None or normalized_value2 is None:
            return None
        return and_(comparable_expression >= normalized_value, comparable_expression <= normalized_value2)
    if operator == "in":
        values = _coerce_filter_list_value(value, value_type)
        if values and value_type == "text":
            return func.lower(text_expression).in_([str(item).lower() for item in values])
        return comparable_expression.in_(values) if values else None
    if operator in {"gt", "gte", "lt", "lte", "equals", "notEquals"}:
        if normalized_value is None:
            return None
        if operator == "gt":
            return comparable_expression > normalized_value
        if operator == "gte":
            return comparable_expression >= normalized_value
        if operator == "lt":
            return comparable_expression < normalized_value
        if operator == "lte":
            return comparable_expression <= normalized_value
        if operator == "equals":
            return comparable_expression == normalized_value
        return comparable_expression != normalized_value

    return None


def _normalize_filter_operator(operator):
    if not isinstance(operator, str):
        return operator
    return {
        "starts-with": "startsWith",
        "ends-with": "endsWith",
        "not-equals": "notEquals",
        "is-null": "isNull",
        "not-null": "notNull",
        "is-empty": "isEmpty",
        "not-empty": "notEmpty",
    }.get(operator, operator)


def _safe_text_search_expression(key: str | None):
    expression, value_type = _grid_column_expression(key)
    return expression if value_type == "text" else None


def _is_search_text_allowed(value: object) -> bool:
    return value is not None and len(str(value).strip()) >= MIN_TEXT_SEARCH_LENGTH


def _quick_filter_predicate(payload):
    if not isinstance(payload, dict):
        return None
    query = payload.get("query")
    if query is None or not str(query).strip():
        return None

    mode = payload.get("mode") if payload.get("mode") in {"contains", "tokens"} else "contains"
    if mode == "tokens":
        terms = [term for term in str(query).strip().lower().split() if term]
    else:
        terms = [str(query).strip().lower()]
    if not terms:
        return None

    columns = payload.get("columns")
    column_keys = [str(column) for column in columns if isinstance(column, str)] if isinstance(columns, list) else list(DEFAULT_QUICK_FILTER_COLUMNS)
    expressions = [_quick_filter_text_expression(column_key) for column_key in column_keys]
    expressions = [expression for expression in expressions if expression is not None]
    if not expressions:
        return None

    term_predicates = []
    for term in terms:
        pattern = f"%{_escape_like(term)}%"
        term_predicates.append(or_(*(expression.like(pattern, escape="\\") for expression in expressions)))
    return and_(*term_predicates)


def _quick_filter_text_expression(key: str):
    expression, _ = _grid_column_expression(key)
    if expression is None:
        return None
    return func.lower(func.coalesce(cast(expression, String), ""))


def _grid_filter_has_quick_filter(filter_model: dict | None) -> bool:
    return _filter_model_has_quick_filter(filter_model)


def _filter_model_has_quick_filter(filter_model: dict | None) -> bool:
    if not isinstance(filter_model, dict):
        return False
    quick_filter = filter_model.get("quickFilter")
    return isinstance(quick_filter, dict) and quick_filter.get("query") is not None and bool(str(quick_filter.get("query")).strip())


def _combine_joined_predicates(joined_predicates: list[tuple[str, object]]):
    if not joined_predicates:
        return None
    expression = joined_predicates[0][1]
    for join, predicate in joined_predicates[1:]:
        expression = or_(expression, predicate) if join == "or" else and_(expression, predicate)
    return expression


def _coerce_filter_value(value, value_type: str):
    if value is None:
        return None
    if value_type == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "да"}
    if value_type == "number":
        try:
            return Decimal(str(value).replace(" ", "").replace(",", "."))
        except (DecimalException, ValueError):
            return None
    return str(value) if value_type == "text" else value


def _coerce_filter_list_value(value, value_type: str):
    raw_values = value if isinstance(value, list) else str(value).split(",")
    values = []
    for item in raw_values:
        normalized = _coerce_filter_value(str(item).strip() if item is not None else None, value_type)
        if normalized is not None and normalized not in values:
            values.append(normalized)
    return values


def _value_set_token_predicate(expression, token: str):
    if token == "null":
        return expression.is_(None)
    if token.startswith("string:"):
        # The column menu normalizes string tokens to lower case before applying
        # value-set filters, so the server must use the same lookup semantics.
        return func.lower(cast(expression, String)) == token.removeprefix("string:").lower()
    if token.startswith("number:"):
        try:
            return expression == Decimal(token.removeprefix("number:"))
        except (DecimalException, ValueError):
            return None
    if token.startswith("boolean:"):
        value = token.removeprefix("boolean:").strip().lower()
        if value == "true":
            return expression.is_(True)
        if value == "false":
            return expression.is_(False)
        return None
    return cast(expression, String) == token


def _value_set_tokens_predicate(expression, tokens: list[str]):
    string_values: list[str] = []
    number_values: list[Decimal] = []
    boolean_values: list[bool] = []
    raw_values: list[str] = []
    include_null = False

    for token in tokens:
        if token == "null":
            include_null = True
            continue
        if token.startswith("string:"):
            string_values.append(token.removeprefix("string:").lower())
            continue
        if token.startswith("number:"):
            try:
                number_values.append(Decimal(token.removeprefix("number:")))
            except (DecimalException, ValueError):
                continue
            continue
        if token.startswith("boolean:"):
            value = token.removeprefix("boolean:").strip().lower()
            if value == "true":
                boolean_values.append(True)
            elif value == "false":
                boolean_values.append(False)
            continue
        raw_values.append(token)

    predicates = []
    if include_null:
        predicates.append(expression.is_(None))
    if string_values:
        predicates.append(func.lower(cast(expression, String)).in_(string_values))
    if number_values:
        predicates.append(expression.in_(number_values))
    if boolean_values:
        predicates.append(expression.in_(boolean_values))
    if raw_values:
        predicates.append(cast(expression, String).in_(raw_values))
    if not predicates:
        return None
    return or_(*predicates)


def _histogram_limit(value: object) -> int:
    try:
        return min(250, max(1, int(value or 50)))
    except (TypeError, ValueError):
        return 50


def _serialize_histogram_token(value: object, value_type: str) -> str:
    if value is None:
        return "null"
    if value_type == "boolean" or isinstance(value, bool):
        return f"boolean:{str(bool(value)).lower()}"
    if value_type == "number" or isinstance(value, int | float | Decimal):
        return f"number:{value}"
    return f"string:{_histogram_text_value(value)}"


def _histogram_json_value(value: object) -> object:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _histogram_text_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _pagination_from_total(
    total: int,
    *,
    page: int,
    page_size: int,
    offset: int | None = None,
) -> LotDatagridPagination:
    safe_page = max(1, page)
    safe_page_size = max(1, page_size)
    total_pages = max(1, (total + safe_page_size - 1) // safe_page_size)
    if offset is not None:
        safe_page = min(max(1, (max(0, offset) // safe_page_size) + 1), total_pages)
    return LotDatagridPagination(
        page=min(safe_page, total_pages),
        page_size=safe_page_size,
        total=total,
        total_pages=total_pages,
    )


def _shortlist_record_predicate():
    shortlist_decision_exists = (
        select(AuctionLotWorkItem.id)
        .where(AuctionLotWorkItem.lot_record_id == AuctionLotRecord.id)
        .where(func.lower(func.coalesce(AuctionLotWorkItem.decision_status, "")).in_(SHORTLIST_DECISIONS))
        .exists()
    )
    return or_(AuctionLotRecord.rating_score >= SHORTLIST_MIN_SCORE, shortlist_decision_exists)


def _json_text_value(key: str):
    return AuctionLotRecord.datagrid_row[key].as_string()


def _json_nested_text_value(first_key: str, second_key: str):
    return AuctionLotRecord.datagrid_row[first_key][second_key].as_string()


def _json_decimal_value(key: str):
    cleaned = func.regexp_replace(_json_text_value(key), "[^0-9,.-]+", "", "g")
    normalized = func.replace(cleaned, ",", ".")
    return cast(func.nullif(normalized, ""), Numeric(14, 2))


def _json_integer_value(key: str):
    cleaned = func.regexp_replace(_json_text_value(key), "[^0-9-]+", "", "g")
    return cast(func.nullif(cleaned, ""), Integer)


def _json_boolean_value(key: str):
    return AuctionLotRecord.datagrid_row[key].as_boolean()


def _grid_total_expenses_value():
    return (
        func.coalesce(_json_decimal_value("platform_fee"), 0)
        + func.coalesce(_json_decimal_value("delivery_cost"), 0)
        + func.coalesce(_json_decimal_value("dismantling_cost"), 0)
        + func.coalesce(_json_decimal_value("repair_cost"), 0)
        + func.coalesce(_json_decimal_value("storage_cost"), 0)
        + func.coalesce(_json_decimal_value("legal_cost"), 0)
        + func.coalesce(_json_decimal_value("other_costs"), 0)
    )


def _grid_full_entry_cost_value():
    price = _json_decimal_value("current_price_value")
    return case(
        (price.is_(None), None),
        else_=price + _grid_total_expenses_value(),
    )


def _grid_potential_profit_value():
    market_value = _json_decimal_value("market_value")
    full_entry_cost = _grid_full_entry_cost_value()
    return case(
        (market_value.is_(None), None),
        (full_entry_cost.is_(None), None),
        else_=market_value - full_entry_cost,
    )


def _grid_roi_value():
    full_entry_cost = _grid_full_entry_cost_value()
    return case(
        (full_entry_cost.is_(None), None),
        (full_entry_cost == 0, None),
        else_=_grid_potential_profit_value() / full_entry_cost,
    )


def _work_item_text_value(key: str):
    return (
        select(getattr(AuctionLotWorkItem, key))
        .where(AuctionLotWorkItem.lot_record_id == AuctionLotRecord.id)
        .limit(1)
        .scalar_subquery()
    )


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _default_row_sort_key(row: LotDatagridRow) -> tuple[str, int, str, str]:
    return (
        row.source,
        row.source_position if row.source_position is not None else LOT_DATASET_MAX_ROWS,
        row.auction_id or "",
        row.lot_id or "",
    )


def paginate_rows(
    rows: list[LotDatagridRow],
    *,
    page: int,
    page_size: int,
) -> tuple[list[LotDatagridRow], LotDatagridPagination]:
    safe_page = max(1, page)
    safe_page_size = max(1, page_size)
    total = len(rows)
    total_pages = max(1, (total + safe_page_size - 1) // safe_page_size)
    resolved_page = min(safe_page, total_pages)
    start = (resolved_page - 1) * safe_page_size
    end = start + safe_page_size
    return rows[start:end], LotDatagridPagination(
        page=resolved_page,
        page_size=safe_page_size,
        total=total,
        total_pages=total_pages,
    )


def _period_cutoff(period: str) -> datetime:
    days = LOT_PERIOD_DAYS.get(period, LOT_PERIOD_DAYS["month"])
    return datetime.now(timezone.utc) - timedelta(days=days)


async def _work_items_by_record_id(
    session: AsyncSession,
    record_ids: list[int],
) -> dict[int, AuctionLotWorkItem]:
    if not record_ids:
        return {}
    statement = select(AuctionLotWorkItem).where(AuctionLotWorkItem.lot_record_id.in_(record_ids))
    return {work_item.lot_record_id: work_item for work_item in (await session.scalars(statement)).all()}


async def _detail_caches_by_record_id(
    session: AsyncSession,
    record_ids: list[int],
) -> dict[int, AuctionLotDetailCache]:
    if not record_ids:
        return {}
    statement = select(AuctionLotDetailCache).where(AuctionLotDetailCache.lot_record_id.in_(record_ids))
    return {detail_cache.lot_record_id: detail_cache for detail_cache in (await session.scalars(statement)).all()}


def _select_providers(source: str | None):
    if not source or source == "all":
        return list(SOURCE_PROVIDERS.values())
    if source not in SOURCE_PROVIDERS:
        supported = ", ".join(sorted(SOURCE_PROVIDERS))
        raise ValueError(f"Unsupported auction source '{source}'. Supported: {supported}")
    return [SOURCE_PROVIDERS[source]]


def _hydrate_row_from_normalized_item(row: LotDatagridRow, normalized_item: dict | None) -> None:
    if not normalized_item:
        return

    lot = normalized_item.get("lot") or {}
    auction = normalized_item.get("auction") or {}
    debtor = normalized_item.get("debtor") or {}

    row.category = row.category or lot.get("category")
    row.lot_description = row.lot_description or lot.get("description")
    row.price_schedule = row.price_schedule or lot.get("price_schedule") or []
    row.images = row.images or lot.get("images") or []
    row.primary_image_url = row.primary_image_url or lot.get("primary_image_url")
    row.image_count = row.image_count or len(row.images)
    if row.source_position is None and isinstance(normalized_item.get("source_position"), int):
        row.source_position = normalized_item["source_position"]
    row.debtor_name = row.debtor_name or debtor.get("name")
    row.auction_name = row.auction_name or auction.get("name")


def _hydrate_row_from_detail_cache(row: LotDatagridRow, detail_cache: AuctionLotDetailCache | None) -> None:
    if detail_cache is None:
        return
    lot_detail = detail_cache.lot_detail or {}
    lot = lot_detail.get("lot") or {}
    raw_fields = lot_detail.get("raw_fields") or []
    row.category = row.category or lot.get("category") or _raw_field_value(raw_fields, "Категория площадки", "Категория")
    if row.market_value is None:
        row.market_value = parse_price(
            lot.get("market_value")
            or _raw_field_value(
                raw_fields,
                "Кадастровая стоимость",
                "Кадастровая стоимость объекта",
                "Кадастровая стоимость имущества",
                "Кадастровая стоимость на дату оценки",
            )
        )
    for payload in (detail_cache.auction_detail or {}, lot_detail):
        auction = payload.get("auction") or {}
        row.application_deadline = row.application_deadline or auction.get("application_deadline")
        row.auction_date = row.auction_date or auction.get("auction_date")
    row.model_category = row.model_category or row.analysis.category
    _apply_display_category(row)


def _apply_display_category(row: LotDatagridRow) -> None:
    row.category = row.category or row.model_category or row.analysis.category


def _raw_field_value(fields: list[dict], *names: str) -> str | None:
    wanted = {name.lower().rstrip(":") for name in names}
    for field in fields:
        field_name = str(field.get("name") or "").lower().rstrip(":")
        value = field.get("value")
        if field_name in wanted and isinstance(value, str) and value.strip():
            return value.strip()
    return None


def build_datagrid_row(item: AuctionListItem, source_title: str) -> LotDatagridRow:
    initial_price_value = parse_price(item.lot.initial_price)
    current_price_value = parse_price(item.lot.current_price or item.lot.initial_price)
    minimum_price_value = parse_price(item.lot.minimum_price)
    market_value = parse_price(item.lot.market_value)
    freshness = LotFreshness()
    rating = calculate_list_lot_rating(item, current_price_value)
    row_id = f"{item.source}:{item.auction.external_id or item.auction.number}:{item.lot.external_id or item.lot.number}"

    return LotDatagridRow(
        row_id=row_id,
        source=item.source,
        source_title=source_title,
        auction_id=item.auction.external_id,
        auction_number=item.auction.number,
        auction_name=item.auction.name,
        auction_url=item.auction.url,
        publication_date=item.auction.publication_date,
        lot_id=item.lot.external_id,
        lot_number=item.lot.number,
        lot_name=item.lot.name,
        lot_description=item.lot.description,
        lot_url=item.lot.url,
        category=item.lot.category,
        location=item.lot.location,
        location_region=item.lot.region,
        location_city=item.lot.city,
        location_address=item.lot.address,
        location_coordinates=item.lot.coordinates,
        debtor_name=item.debtor.name if item.debtor else None,
        model_category=None,
        status=item.lot.status,
        initial_price=item.lot.initial_price,
        initial_price_value=initial_price_value,
        current_price=item.lot.current_price or item.lot.initial_price,
        current_price_value=current_price_value,
        minimum_price=item.lot.minimum_price,
        minimum_price_value=minimum_price_value,
        price_schedule=item.lot.price_schedule,
        images=item.lot.images,
        primary_image_url=item.lot.primary_image_url,
        image_count=len(item.lot.images),
        organizer_name=item.organizer.name,
        application_deadline=item.auction.application_deadline,
        auction_date=item.auction.auction_date,
        market_value=market_value,
        platform_fee=None,
        delivery_cost=None,
        dismantling_cost=None,
        repair_cost=None,
        storage_cost=None,
        legal_cost=None,
        other_costs=None,
        target_profit=None,
        total_expenses=None,
        full_entry_cost=None,
        potential_profit=None,
        roi=None,
        market_discount=(Decimal("1") - (current_price_value / market_value)) if current_price_value is not None and market_value else None,
        formula_max_purchase_price=None,
        exclude_from_analysis=False,
        exclusion_reason=None,
        freshness=freshness,
        rating=rating,
    )


def _matches_filters(row: LotDatagridRow, filters: LotDatagridFilters) -> bool:
    if filters.status and row.status != filters.status:
        return False
    if filters.min_price is not None and (row.initial_price_value is None or row.initial_price_value < filters.min_price):
        return False
    if filters.max_price is not None and (row.initial_price_value is None or row.initial_price_value > filters.max_price):
        return False
    if filters.only_new and not row.freshness.is_new:
        return False
    if filters.min_rating is not None and row.rating.score < filters.min_rating:
        return False
    return True


def _is_shortlist_candidate(row: LotDatagridRow, work_item: AuctionLotWorkItem | None) -> bool:
    if row.rating.score >= SHORTLIST_MIN_SCORE:
        return True
    decision = (work_item.decision_status or "").strip().lower() if work_item else ""
    return decision in SHORTLIST_DECISIONS


def _attach_work_item_state(row: LotDatagridRow, work_item: AuctionLotWorkItem | None) -> None:
    row.work_decision_status = work_item.decision_status if work_item else None
