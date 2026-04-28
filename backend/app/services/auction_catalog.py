from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auction import AuctionLotRecord, AuctionLotWorkItem
from app.schemas.auctions import (
    AuctionListItem,
    DatagridColumn,
    LotDatagridFilters,
    LotDatagridPagination,
    LotDatagridResponse,
    LotDatagridRow,
    LotFreshness,
    LotRating,
)
from app.services.auction_sources import SOURCE_PROVIDERS, list_source_infos


LOT_GRID_COLUMNS = [
    DatagridColumn(key="rating.score", title="Рейтинг", data_type="number", width=96),
    DatagridColumn(key="freshness.is_new", title="Новый", data_type="boolean", width=84),
    DatagridColumn(key="source_title", title="Площадка", width=120),
    DatagridColumn(key="auction_number", title="Аукцион", width=120),
    DatagridColumn(key="publication_date", title="Дата публикации", data_type="datetime", width=160),
    DatagridColumn(key="lot_number", title="Лот", width=80),
    DatagridColumn(key="lot_name", title="Наименование", width=420),
    DatagridColumn(key="initial_price_value", title="Цена", data_type="money", width=140),
    DatagridColumn(key="status", title="Статус", width=160),
    DatagridColumn(key="organizer_name", title="Организатор", width=220),
    DatagridColumn(key="application_deadline", title="Прием заявок до", data_type="datetime", width=180),
    DatagridColumn(key="auction_date", title="Дата торгов", data_type="datetime", width=180),
]

SHORTLIST_DECISIONS = {"watch", "calculate", "inspection", "bid"}
SHORTLIST_MIN_SCORE = 85
LOT_DATASET_MAX_ROWS = 10_000
LOT_PERIOD_DAYS = {
    "week": 7,
    "month": 31,
    "year": 365,
}


def list_lots_for_datagrid(
    *,
    period: str = "month",
    source: str | None = None,
    q: str | None = None,
    status: str | None = None,
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
        q=q,
        status=status,
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
    q: str | None = None,
    status: str | None = None,
    min_price: Decimal | None = None,
    max_price: Decimal | None = None,
    only_new: bool = False,
    shortlist: bool = False,
    min_rating: int | None = None,
    page: int = 1,
    page_size: int = 100,
) -> LotDatagridResponse:
    safe_page_size = min(page_size, LOT_DATASET_MAX_ROWS)
    filters = LotDatagridFilters(
        period=period,
        source=source,
        q=q,
        status=status,
        min_price=min_price,
        max_price=max_price,
        only_new=only_new,
        shortlist=shortlist,
        min_rating=min_rating,
    )
    statement = select(AuctionLotRecord).order_by(AuctionLotRecord.last_seen_at.desc())
    statement = statement.where(AuctionLotRecord.last_seen_at >= _period_cutoff(period))
    if source and source != "all":
        statement = statement.where(AuctionLotRecord.source_code == source)
    if status:
        statement = statement.where(AuctionLotRecord.status == status)
    if only_new:
        statement = statement.where(AuctionLotRecord.is_new.is_(True))
    if min_rating is not None:
        statement = statement.where(AuctionLotRecord.rating_score >= min_rating)
    statement = statement.limit(LOT_DATASET_MAX_ROWS)
    records = (await session.scalars(statement)).all()
    work_items = await _work_items_by_record_id(session, [record.id for record in records])
    matched_rows: list[LotDatagridRow] = []
    for record in records:
        row = LotDatagridRow.model_validate(record.datagrid_row)
        work_item = work_items.get(record.id)
        _attach_work_item_state(row, work_item)
        if filters.shortlist and not _is_shortlist_candidate(row, work_item):
            continue
        if _matches_filters(row, filters):
            matched_rows.append(row)

    paged_rows, pagination = paginate_rows(matched_rows, page=page, page_size=safe_page_size)

    return LotDatagridResponse(
        columns=LOT_GRID_COLUMNS,
        rows=paged_rows,
        filters=filters,
        total=pagination.total,
        pagination=pagination,
        available_sources=list_source_infos(),
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


def _select_providers(source: str | None):
    if not source or source == "all":
        return list(SOURCE_PROVIDERS.values())
    if source not in SOURCE_PROVIDERS:
        supported = ", ".join(sorted(SOURCE_PROVIDERS))
        raise ValueError(f"Unsupported auction source '{source}'. Supported: {supported}")
    return [SOURCE_PROVIDERS[source]]


def build_datagrid_row(item: AuctionListItem, source_title: str) -> LotDatagridRow:
    price_value = parse_price(item.lot.initial_price)
    freshness = LotFreshness()
    rating = calculate_lot_rating(item, price_value)
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
        lot_url=item.lot.url,
        category=item.lot.category,
        status=item.lot.status,
        initial_price=item.lot.initial_price,
        initial_price_value=price_value,
        organizer_name=item.organizer.name,
        application_deadline=item.auction.application_deadline,
        auction_date=item.auction.auction_date,
        freshness=freshness,
        rating=rating,
    )


def parse_price(value: str | None) -> Decimal | None:
    if not value:
        return None
    normalized = value.replace(" ", "").replace("\xa0", "").replace(",", ".")
    normalized = "".join(char for char in normalized if char.isdigit() or char == ".")
    if not normalized:
        return None
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


def calculate_lot_rating(item: AuctionListItem, price_value: Decimal | None) -> LotRating:
    score = 50
    reasons: list[str] = ["Базовая оценка до подключения пользовательской модели рейтинга"]
    status = (item.lot.status or "").lower()

    if "приём" in status or "прием" in status:
        score += 25
        reasons.append("Идет прием заявок")
    if "отмен" in status:
        score -= 45
        reasons.append("Лот отменен")
    if price_value is not None:
        score += 10
        reasons.append("Цена распознана и доступна для фильтрации")
    if item.auction.application_deadline:
        score += 5
        reasons.append("Есть срок окончания приема заявок")

    score = max(0, min(100, score))
    if score >= 75:
        level = "high"
    elif score >= 45:
        level = "medium"
    else:
        level = "low"

    return LotRating(score=score, level=level, reasons=reasons)


def _matches_filters(row: LotDatagridRow, filters: LotDatagridFilters) -> bool:
    if filters.q:
        query = filters.q.lower()
        haystack = " ".join(
            value or ""
            for value in [row.lot_name, row.auction_name, row.organizer_name, row.auction_number, row.status]
        ).lower()
        if query not in haystack:
            return False
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
