from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from affino_grid_backend import ApiException
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.procurement_grid import (
    ProcurementLotsGridEditResponse,
    ProcurementLotsGridFillRequest,
    ProcurementLotsGridPullRow,
)
from app.services.procurement_grid import build_procurement_grid_row, pull_procurement_lots_for_grid
from app.services.procurement_grid_edits import ProcurementGridEditConflictError
from app.services.procurement_grid_state import DEFAULT_GRID_WORKSPACE_ID, PROCUREMENT_LOTS_TABLE_ID, procurement_lot_grid_row_id


@dataclass(frozen=True)
class GridBackendFillRange:
    startRow: int
    endRow: int
    startColumn: int = 0
    endColumn: int = 0

    def model_dump(self, *, by_alias: bool = False) -> dict[str, int]:
        del by_alias
        return {
            "startRow": self.startRow,
            "endRow": self.endRow,
            "startColumn": self.startColumn,
            "endColumn": self.endColumn,
        }


@dataclass(frozen=True)
class GridBackendFillRequest:
    mode: str
    source_row_ids: list[str]
    target_row_ids: list[str]
    fill_columns: list[str]
    reference_columns: list[str]
    source_range: GridBackendFillRange
    target_range: GridBackendFillRange
    projection: dict[str, Any]
    metadata: dict[str, Any] | None = None
    operation_id: str | None = None
    base_version: int | None = None
    workspace_id: str = DEFAULT_GRID_WORKSPACE_ID
    user_id: str | None = None
    session_id: str | None = None


async def commit_procurement_lot_grid_fill(
    session: AsyncSession,
    request: ProcurementLotsGridFillRequest,
    *,
    workspace_id: str = DEFAULT_GRID_WORKSPACE_ID,
    user_id: str | None = None,
    session_id: str | None = None,
) -> ProcurementLotsGridEditResponse:
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

    rows, total = await pull_procurement_lots_for_grid(session, start_row=fetch_start, end_row=fetch_end)
    if fetch_end > total:
        raise ValueError("Fill ranges are out of bounds")

    source_rows = rows[source.start_row - fetch_start : source.end_row - fetch_start]
    target_rows = rows[target.start_row - fetch_start : target.end_row - fetch_start]
    if not source_rows or not target_rows:
        raise ValueError("Fill ranges must not be empty")
    if len(source_rows) not in {1, len(target_rows)}:
        raise ValueError("Copy fill requires a single source row or a source range matching the target size")

    payload = request.model_dump(by_alias=True, mode="json")
    payload["edits"] = [
        {
            "rowId": procurement_lot_grid_row_id(target_record),
            "columnId": target.column_id,
            "value": (source_rows[0] if len(source_rows) == 1 else source_rows[index])[1].get(source.column_id),
        }
        for index, (target_record, _) in enumerate(target_rows)
    ]
    backend_request = GridBackendFillRequest(
        mode=request.mode,
        source_row_ids=[procurement_lot_grid_row_id(record) for record, _ in source_rows],
        target_row_ids=[procurement_lot_grid_row_id(record) for record, _ in target_rows],
        fill_columns=[target.column_id],
        reference_columns=[source.column_id],
        source_range=GridBackendFillRange(startRow=source.start_row, endRow=source.end_row),
        target_range=GridBackendFillRange(startRow=target.start_row, endRow=target.end_row),
        projection={"tableId": PROCUREMENT_LOTS_TABLE_ID},
        metadata=payload,
        base_version=request.base_version,
        workspace_id=workspace_id,
        user_id=user_id,
        session_id=session_id,
    )

    from app.services.grid_backend_fill import ProcurementGridFillService
    from app.services.grid_state import get_dataset_version

    service = ProcurementGridFillService(workspace_id=workspace_id)
    try:
        result = await service.commit_fill(session, backend_request)
    except ApiException as error:
        if error.code == "stale-revision":
            current_version = await get_dataset_version(session, workspace_id, PROCUREMENT_LOTS_TABLE_ID)
            raise ProcurementGridEditConflictError(base_version=request.base_version, current_version=current_version) from error
        if error.status_code == 404:
            raise LookupError(error.message) from error
        raise ValueError(error.message) from error

    return ProcurementLotsGridEditResponse(
        dataset_version=int(result.revision),
        updated_rows=[
            ProcurementLotsGridPullRow(
                id=procurement_lot_grid_row_id(record),
                index=int(record.id or 0),
                row=build_procurement_grid_row(record),
            )
            for record in result.rows
        ],
    )


@dataclass(frozen=True)
class FillSpan:
    start_row: int
    end_row: int
    column_id: str


def _normalize_fill_span(start_row: int, end_row: int, column_id: str, field_name: str) -> FillSpan:
    if start_row < 0 or end_row < 0:
        raise ValueError(f"{field_name} startRow/endRow must be non-negative")
    if end_row <= start_row:
        raise ValueError(f"{field_name} endRow must be greater than startRow")
    normalized_column_id = column_id.strip()
    if not normalized_column_id:
        raise ValueError(f"{field_name} columnId must not be empty")
    return FillSpan(start_row=start_row, end_row=end_row, column_id=normalized_column_id)
