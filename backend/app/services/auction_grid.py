from __future__ import annotations

from copy import deepcopy
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
)
from app.services.auction_catalog import list_persisted_lot_column_histogram, pull_persisted_lots_for_grid
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
    rows, total = await pull_persisted_lots_for_grid(
        session,
        start_row=request.resolved_start_row,
        end_row=request.resolved_end_row,
        period=request.period,
        source=request.source,
        q=request.q,
        status=request.status,
        analysis_color=request.analysis_color,
        min_price=request.min_price,
        max_price=request.max_price,
        only_new=request.only_new,
        shortlist=request.shortlist,
        min_rating=request.min_rating,
        sort_model=_normalize_sort_model(request.sort_model),
        grid_filter=request.filter_model,
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
    )


async def get_auction_lots_grid_histogram(
    session: AsyncSession,
    request: AuctionLotsGridHistogramRequest,
) -> AuctionLotsGridHistogramResponse:
    entries = await list_persisted_lot_column_histogram(
        session,
        period=request.period,
        source=request.source,
        q=request.q,
        status=request.status,
        analysis_color=request.analysis_color,
        min_price=request.min_price,
        max_price=request.max_price,
        only_new=request.only_new,
        shortlist=request.shortlist,
        min_rating=request.min_rating,
        column_id=request.column_id,
        histogram_options=request.options,
        sort_model=_normalize_sort_model(request.sort_model),
        grid_filter=_histogram_filter_model(request.filter_model, request.column_id, request.options),
    )
    return AuctionLotsGridHistogramResponse(column_id=request.column_id, entries=entries)

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
