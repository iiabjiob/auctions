from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.auction_grid import (
    AuctionLotsGridCellEdit,
    AuctionLotsGridEditResponse,
    AuctionLotsGridFillRequest,
)
from app.services.auction_catalog import pull_persisted_lots_for_grid
from app.services.auction_grid_edits import (
    _commit_auction_lot_grid_operations,
    _workspace_field_for_column,
)
from app.services.auction_grid_state import AUCTION_LOTS_TABLE_ID, DEFAULT_GRID_WORKSPACE_ID


@dataclass(frozen=True)
class FillSpan:
    start_row: int
    end_row: int
    column_id: str

    @property
    def length(self) -> int:
        return self.end_row - self.start_row


async def commit_auction_lot_grid_fill(
    session: AsyncSession,
    request: AuctionLotsGridFillRequest,
    *,
    workspace_id: str = DEFAULT_GRID_WORKSPACE_ID,
    user_id: str | None = None,
    session_id: str | None = None,
) -> AuctionLotsGridEditResponse:
    if request.mode != "copy":
        raise ValueError("Only copy fill mode is supported")

    source = _normalize_fill_span(request.source.start_row, request.source.end_row, request.source.column_id, "source")
    target = _normalize_fill_span(request.target.start_row, request.target.end_row, request.target.column_id, "target")
    if source.column_id != target.column_id:
        raise ValueError("Fill source and target must use the same column")

    fetch_start = min(source.start_row, target.start_row)
    fetch_end = max(source.end_row, target.end_row)
    if fetch_end <= fetch_start:
        raise ValueError("Fill ranges must not be empty")

    rows, total = await pull_persisted_lots_for_grid(
        session,
        start_row=fetch_start,
        end_row=fetch_end,
    )
    if fetch_end > total:
        raise ValueError("Fill ranges are out of bounds")

    source_rows = rows[source.start_row - fetch_start : source.end_row - fetch_start]
    target_rows = rows[target.start_row - fetch_start : target.end_row - fetch_start]
    if not source_rows or not target_rows:
        raise ValueError("Fill ranges must not be empty")

    if len(source_rows) not in {1, len(target_rows)}:
        raise ValueError("Copy fill requires a single source row or a source range matching the target size")

    field_name = _workspace_field_for_column(source.column_id)
    edits: list[AuctionLotsGridCellEdit] = []
    for index, (_, target_row) in enumerate(target_rows):
        source_row = source_rows[0] if len(source_rows) == 1 else source_rows[index]
        _, source_datagrid_row = source_row
        value = getattr(source_datagrid_row, field_name)
        edits.append(
            AuctionLotsGridCellEdit(
                row_id=target_row.row_id,
                column_id=target.column_id,
                value=value,
            )
        )

    payload = request.model_dump(by_alias=True, mode="json")
    payload["edits"] = [edit.model_dump(by_alias=True, mode="json") for edit in edits]
    return await _commit_auction_lot_grid_operations(
        session,
        base_version=request.base_version,
        edits=edits,
        workspace_id=workspace_id,
        user_id=user_id,
        session_id=session_id,
        operation_type="fill",
        payload=payload,
    )


def _normalize_fill_span(start_row: int, end_row: int, column_id: str, field_name: str) -> FillSpan:
    if start_row < 0 or end_row < 0:
        raise ValueError(f"{field_name} startRow/endRow must be non-negative")
    if end_row <= start_row:
        raise ValueError(f"{field_name} endRow must be greater than startRow")
    normalized_column_id = column_id.strip()
    if not normalized_column_id:
        raise ValueError(f"{field_name} columnId must not be empty")
    return FillSpan(start_row=start_row, end_row=end_row, column_id=normalized_column_id)
