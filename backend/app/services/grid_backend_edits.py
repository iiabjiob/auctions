from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from affino_grid_backend import ApiException, GridEditServiceBase
from affino_grid_backend.core.mutations import GridHistoryStatus, PendingGridCellEvent
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.grid import GridCellEventModel, GridChangeEventModel, GridOperationModel
from app.models.procurement import ProcurementLotRecord, _sync_procurement_lot_search_text
from app.services.grid_backend_history import ProcurementGridRevisionService
from app.services.grid_state import clear_redo_grid_operations
from app.services.grid_table_registry import get_grid_table_definition
from app.services.procurement_calculator import (
    calculator_field_for_column,
    coerce_calculator_input_value,
    recalculate_procurement_lot,
)
from app.services.procurement_grid_edits import (
    CALCULATION_TRIGGER_RECORD_FIELDS,
    _calculator_input_value,
    _coerce_value,
    _parse_row_id,
    _procurement_field_for_column,
    _set_calculator_input_value,
)
from app.services.procurement_grid_state import (
    DEFAULT_GRID_WORKSPACE_ID,
    PROCUREMENT_LOTS_TABLE_ID,
    procurement_lot_grid_row_id,
)
from app.services.procurement_notifications import enqueue_procurement_telegram_notifications
from app.services.procurement_scoring import apply_procurement_score


@dataclass(frozen=True)
class GridBackendCellEdit:
    row_id: str
    column_id: str
    value: Any
    previous_value: Any = None


@dataclass(frozen=True)
class GridBackendEditRequest:
    base_revision: str | None
    edits: list[GridBackendCellEdit]
    base_version: int | None = None
    payload: dict[str, Any] | None = None
    workspace_id: str = DEFAULT_GRID_WORKSPACE_ID
    user_id: str | None = None
    session_id: str | None = None
    operation_type: str = "edit"
    operation_id: str | None = None


class ProcurementGridEditService(GridEditServiceBase):
    def __init__(self, *, workspace_id: str = DEFAULT_GRID_WORKSPACE_ID) -> None:
        self.workspace_id = workspace_id
        super().__init__(
            get_grid_table_definition(PROCUREMENT_LOTS_TABLE_ID),
            ProcurementGridRevisionService(workspace_id=workspace_id),  # type: ignore[arg-type]
        )

    def create_edit_operation_id(self) -> str:
        return str(uuid4())

    async def fetch_rows_by_ids(
        self,
        session: AsyncSession,
        row_ids: list[str],
        *,
        with_for_update: bool = False,
    ) -> dict[str, ProcurementLotRecord]:
        rows: dict[str, ProcurementLotRecord] = {}
        for row_id in row_ids:
            source_code, external_id = _parse_row_id(row_id)
            statement = select(ProcurementLotRecord).where(
                ProcurementLotRecord.source_code == source_code,
                ProcurementLotRecord.external_id == external_id,
            )
            if with_for_update:
                statement = statement.with_for_update()
            record = await session.scalar(statement)
            if record is not None:
                rows[procurement_lot_grid_row_id(record)] = record
        return rows

    async def ensure_operation_id_available(self, session: AsyncSession, operation_id: str) -> None:
        operation_uuid = _operation_uuid(operation_id)
        existing_id = await session.scalar(select(GridOperationModel.id).where(GridOperationModel.id == operation_uuid))
        if existing_id is not None:
            raise ApiException(status_code=409, code="operation-id-conflict", message="Operation id already exists")

    async def create_operation(
        self,
        session: AsyncSession,
        operation_id: str,
        changed_at: datetime,
        request: GridBackendEditRequest,
    ) -> None:
        await clear_redo_grid_operations(
            session,
            workspace_id=request.workspace_id,
            table_id=PROCUREMENT_LOTS_TABLE_ID,
            user_id=request.user_id,
            session_id=request.session_id,
        )
        session.add(
            GridOperationModel(
                id=_operation_uuid(operation_id),
                workspace_id=request.workspace_id,
                table_id=PROCUREMENT_LOTS_TABLE_ID,
                user_id=request.user_id,
                session_id=request.session_id,
                operation_type=request.operation_type,
                base_version=request.base_version,
                payload=request.payload or {},
                created_at=changed_at,
            )
        )

    async def create_cell_events(
        self,
        session: AsyncSession,
        operation_id: str,
        cell_events: list[PendingGridCellEvent],
        changed_at: datetime,
    ) -> None:
        del changed_at
        operation_uuid = _operation_uuid(operation_id)
        undo_edits: list[dict[str, Any]] = []
        redo_edits: list[dict[str, Any]] = []
        for event in cell_events:
            field_name = _procurement_history_field(event.column_id)
            session.add(
                GridCellEventModel(
                    operation_id=operation_uuid,
                    workspace_id=self.workspace_id,
                    table_id=PROCUREMENT_LOTS_TABLE_ID,
                    row_id=event.row_id,
                    column_id=event.column_id,
                    before_value={"value": _json_value(event.before_value)},
                    after_value={"value": _json_value(event.after_value)},
                )
            )
            target = "calculator" if calculator_field_for_column(event.column_id) is not None else "record"
            undo_edits.append(
                {
                    "rowId": event.row_id,
                    "columnId": event.column_id,
                    "field": field_name,
                    "target": target,
                    "value": _json_value(event.before_value),
                }
            )
            redo_edits.append(
                {
                    "rowId": event.row_id,
                    "columnId": event.column_id,
                    "field": field_name,
                    "target": target,
                    "value": _json_value(event.after_value),
                }
            )
        operation = await session.scalar(select(GridOperationModel).where(GridOperationModel.id == operation_uuid).with_for_update())
        if operation is not None:
            operation.undo_payload = {"edits": undo_edits}
            operation.redo_payload = {"edits": redo_edits}
        await session.flush()

    def get_row_value(self, row: ProcurementLotRecord, column_id: str) -> Any:
        calculator_field = calculator_field_for_column(column_id)
        if calculator_field is not None:
            return _calculator_input_value(row, calculator_field)
        return getattr(row, _procurement_field_for_column(column_id))

    def set_row_value(self, row: ProcurementLotRecord, column_id: str, value: Any) -> None:
        calculator_field = calculator_field_for_column(column_id)
        should_recalculate = False
        if calculator_field is not None:
            _set_calculator_input_value(row, calculator_field, value)
            should_recalculate = True
        else:
            field_name = _procurement_field_for_column(column_id)
            setattr(row, field_name, value)
            should_recalculate = field_name in CALCULATION_TRIGGER_RECORD_FIELDS
        if should_recalculate:
            recalculate_procurement_lot(row)
        apply_procurement_score(row)
        _sync_procurement_lot_search_text(None, None, row)

    def get_row_id(self, row: ProcurementLotRecord) -> str:
        return procurement_lot_grid_row_id(row)

    def get_row_index(self, row: ProcurementLotRecord) -> int:
        return int(row.id or 0)

    def set_row_updated_at(self, row: ProcurementLotRecord, changed_at: datetime) -> None:
        row.updated_at = changed_at

    def get_row_revision(self, row: ProcurementLotRecord) -> str:
        if row.updated_at is None:
            return str(row.id or "")
        return row.updated_at.isoformat()

    def normalize_edit_value(self, column_id: str, value: Any) -> Any:
        calculator_field = calculator_field_for_column(column_id)
        try:
            if calculator_field is not None:
                return coerce_calculator_input_value(calculator_field, value)
            field_name = _procurement_field_for_column(column_id)
            return _coerce_value(field_name, value)
        except ValueError as error:
            raise ApiException(status_code=400, code="invalid-value", message=str(error)) from error

    async def collect_history_status(
        self,
        session: AsyncSession,
        request: GridBackendEditRequest,
        *,
        operation_id: str | None,
        committed: list[Any],
        committed_row_ids: list[str],
        rejected: list[Any],
        affected_indexes: list[int],
        revision: str,
        rows: list[ProcurementLotRecord] | None = None,
    ) -> GridHistoryStatus | None:
        del committed, committed_row_ids, rejected, affected_indexes
        dataset_version = int(revision)
        if operation_id is not None:
            operation = await session.scalar(
                select(GridOperationModel).where(GridOperationModel.id == _operation_uuid(operation_id)).with_for_update()
            )
            if operation is not None:
                operation.resulting_version = dataset_version
        for row in rows or []:
            row_id = procurement_lot_grid_row_id(row)
            await enqueue_procurement_telegram_notifications(session, row)
            session.add(
                GridChangeEventModel(
                    workspace_id=request.workspace_id,
                    table_id=PROCUREMENT_LOTS_TABLE_ID,
                    dataset_version=dataset_version,
                    event_type="row_updated",
                    row_id=row_id,
                    payload={"source": "grid_edit", "changed_fields": _changed_fields_for_row(row_id, request.edits)},
                )
            )
        return None


def procurement_backend_edit_request(
    *,
    base_version: int,
    edits: list[Any],
    workspace_id: str,
    user_id: str | None,
    session_id: str | None,
    operation_type: str = "edit",
    payload: dict[str, Any] | None = None,
) -> GridBackendEditRequest:
    return GridBackendEditRequest(
        base_revision=str(base_version),
        base_version=base_version,
        workspace_id=workspace_id,
        user_id=user_id,
        session_id=session_id,
        operation_type=operation_type,
        payload=payload,
        edits=[
            GridBackendCellEdit(
                row_id=edit.row_id,
                column_id=edit.column_id,
                value=edit.value,
            )
            for edit in edits
        ],
    )


def _operation_uuid(operation_id: str) -> UUID:
    try:
        return UUID(str(operation_id))
    except ValueError as error:
        raise ApiException(status_code=400, code="invalid-operation-id", message="operation_id must be a UUID") from error


def _procurement_history_field(column_id: str) -> str:
    calculator_field = calculator_field_for_column(column_id)
    if calculator_field is not None:
        return calculator_field
    return _procurement_field_for_column(column_id)


def _changed_fields_for_row(row_id: str, edits: list[GridBackendCellEdit]) -> list[str]:
    fields = {
        _procurement_history_field(edit.column_id)
        for edit in edits
        if edit.row_id == row_id
    }
    return sorted(fields)


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value
