from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.grid import GridRevisionModel
from app.schemas.auction_grid import (
    AuctionLotsGridHistogramRequest,
    AuctionLotsGridHistogramResponse,
    AuctionLotsGridPullRequest,
    AuctionLotsGridPullResponse,
    AuctionLotsGridPullRow,
    AuctionLotsGridQueryOptions,
    AuctionLotsGridSummary,
)
from app.services.auction_catalog import (
    list_persisted_lot_column_histogram,
    pull_persisted_lots_for_grid,
    summarize_persisted_lots_for_grid,
)
from app.services.auction_grid_state import AUCTION_LOTS_TABLE_ID, DEFAULT_GRID_WORKSPACE_ID, auction_lot_grid_row_id


async def read_grid_dataset_version(
    session: AsyncSession,
    *,
    workspace_id: str = DEFAULT_GRID_WORKSPACE_ID,
    table_id: str = AUCTION_LOTS_TABLE_ID,
) -> int:
    version = await session.scalar(
        select(GridRevisionModel.dataset_version).where(
            GridRevisionModel.workspace_id == workspace_id,
            GridRevisionModel.table_id == table_id,
        )
    )
    return int(version or 0)


async def pull_auction_lots_grid(
    session: AsyncSession,
    request: AuctionLotsGridPullRequest,
    *,
    workspace_id: str = DEFAULT_GRID_WORKSPACE_ID,
) -> AuctionLotsGridPullResponse:
    dataset_version = await read_grid_dataset_version(session, workspace_id=workspace_id)
    grid_filter = _merge_query_options_into_filter_model(request.filter_model, request)
    rows, total = await pull_persisted_lots_for_grid(
        session,
        start_row=request.resolved_start_row,
        end_row=request.resolved_end_row,
        period=request.period,
        source=None,
        status=None,
        analysis_color=None,
        min_price=None,
        max_price=None,
        only_new=False,
        shortlist=False,
        min_rating=None,
        include_archived=request.include_archived,
        sort_model=_normalize_sort_model(request.sort_model),
        grid_filter=grid_filter,
    )
    summary = await summarize_persisted_lots_for_grid(
        session,
        period=request.period,
        source=None,
        status=None,
        analysis_color=None,
        min_price=None,
        max_price=None,
        only_new=False,
        shortlist=False,
        min_rating=None,
        include_archived=request.include_archived,
        grid_filter=grid_filter,
    )
    return AuctionLotsGridPullResponse(
        rows=[
            AuctionLotsGridPullRow(
                id=auction_lot_grid_row_id(record),
                index=request.resolved_start_row + offset,
                row=row,
            )
            for offset, (record, row) in enumerate(rows)
        ],
        total=total,
        dataset_version=dataset_version,
        summary=summary,
    )


async def get_auction_lots_grid_histogram(
    session: AsyncSession,
    request: AuctionLotsGridHistogramRequest,
) -> AuctionLotsGridHistogramResponse:
    grid_filter = _merge_query_options_into_filter_model(
        _histogram_filter_model(request.filter_model, request.column_id, request.options),
        request,
    )
    if _has_search_query(grid_filter):
        return AuctionLotsGridHistogramResponse(column_id=request.column_id, entries=[])
    entries = await list_persisted_lot_column_histogram(
        session,
        period=request.period,
        source=None,
        status=None,
        analysis_color=None,
        min_price=None,
        max_price=None,
        only_new=False,
        shortlist=False,
        min_rating=None,
        include_archived=request.include_archived,
        column_id=request.column_id,
        histogram_options=request.options,
        sort_model=_normalize_sort_model(request.sort_model),
        grid_filter=grid_filter,
    )
    return AuctionLotsGridHistogramResponse(column_id=request.column_id, entries=entries)


def _merge_query_options_into_filter_model(
    filter_model: dict[str, Any] | None,
    request: AuctionLotsGridQueryOptions,
) -> dict[str, Any] | None:
    expression = _query_options_advanced_expression(request)
    if expression is None:
        return filter_model

    next_filter_model = deepcopy(filter_model) if filter_model else {}
    current_expression = next_filter_model.get("advancedExpression")
    next_filter_model["advancedExpression"] = (
        {
            "kind": "group",
            "operator": "and",
            "children": [current_expression, expression],
        }
        if isinstance(current_expression, dict)
        else expression
    )
    return next_filter_model


def _query_options_advanced_expression(request: AuctionLotsGridQueryOptions) -> dict[str, Any] | None:
    conditions: list[dict[str, Any]] = []
    _append_text_condition(conditions, "source", "equals", request.source if request.source != "all" else None)
    _append_text_condition(conditions, "status", "equals", request.status)
    _append_text_condition(conditions, "analysisColor", "equals", request.analysis_color)
    _append_decimal_condition(conditions, "price", "gte", request.min_price)
    _append_decimal_condition(conditions, "price", "lte", request.max_price)
    if request.only_new:
        conditions.append({"kind": "condition", "key": "isNew", "operator": "equals", "value": True})
    if request.shortlist:
        conditions.append({"kind": "condition", "key": "__shortlist", "operator": "equals", "value": True})
    if request.min_rating is not None:
        conditions.append({"kind": "condition", "key": "ratingScore", "operator": "gte", "value": request.min_rating})

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"kind": "group", "operator": "and", "children": conditions}


def _append_text_condition(conditions: list[dict[str, Any]], key: str, operator: str, value: str | None) -> None:
    if value is None or not str(value).strip():
        return
    conditions.append({"kind": "condition", "key": key, "operator": operator, "value": str(value).strip()})


def _append_decimal_condition(conditions: list[dict[str, Any]], key: str, operator: str, value: Decimal | None) -> None:
    if value is None:
        return
    conditions.append({"kind": "condition", "key": key, "operator": operator, "value": str(value)})


def _has_search_query(filter_model: dict[str, Any] | None) -> bool:
    if not isinstance(filter_model, dict):
        return False
    return _has_quick_filter_query(filter_model)


def _has_quick_filter_query(filter_model: dict[str, Any] | None) -> bool:
    if not isinstance(filter_model, dict):
        return False
    quick_filter = filter_model.get("quickFilter")
    return isinstance(quick_filter, dict) and isinstance(quick_filter.get("query"), str) and bool(quick_filter["query"].strip())


def _normalize_sort_model(sort_model: list[dict[str, Any]] | None) -> list[dict[str, str]] | None:
    normalized: list[dict[str, str]] = []
    for item in sort_model or []:
        if not isinstance(item, dict):
            continue
        key = _first_string(item, "key", "colId", "columnId", "field")
        direction = _first_string(item, "direction", "sort")
        if key and direction in {"asc", "desc"}:
            normalized.append({"key": key, "direction": direction})
    return normalized or None


def _histogram_filter_model(
    filter_model: dict[str, Any] | None,
    column_id: str,
    options: dict[str, Any],
) -> dict[str, Any] | None:
    if not filter_model:
        return None
    if options.get("ignoreSelfFilter") is not True:
        return filter_model

    filtered_model = deepcopy(filter_model)
    for section_key in ("columnFilters", "advancedFilters"):
        section = filtered_model.get(section_key)
        if isinstance(section, dict):
            section.pop(column_id, None)
    return filtered_model


def _first_string(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
