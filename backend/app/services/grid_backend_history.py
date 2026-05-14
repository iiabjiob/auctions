from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from affino_grid_backend import ApiException, GridColumnDefinition, GridHistoryServiceBase, GridTableDefinition
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.grid import GridCellEventModel, GridChangeEventModel, GridOperationModel
from app.models.procurement import ProcurementLotRecord, _sync_procurement_lot_search_text
from app.schemas.grid_history import GridHistoryMutationResponse, GridHistoryStatusResponse
from app.schemas.procurement_grid import ProcurementLotsGridPullRow
from app.services.auction_grid_history import (
    get_auction_lot_grid_history_status,
    redo_auction_lot_grid_history,
    undo_auction_lot_grid_history,
)
from app.services.auction_grid_state import AUCTION_LOTS_TABLE_ID
from app.services.grid_state import get_dataset_version
from app.services.procurement_calculator import (
    CALCULATOR_INPUT_COLUMNS,
    calculator_field_for_column,
    coerce_calculator_input_value,
    recalculate_procurement_lot,
)
from app.services.procurement_grid import build_procurement_grid_row
from app.services.procurement_grid_edits import (
    CALCULATION_TRIGGER_RECORD_FIELDS,
    PROCUREMENT_EDIT_COLUMNS,
    _calculator_input_value,
    _coerce_value,
    _parse_row_id,
    _procurement_field_for_column,
    _set_calculator_input_value,
)
from app.services.procurement_grid_state import (
    PROCUREMENT_LOTS_TABLE_ID,
    bump_procurement_lot_dataset_version,
    procurement_lot_grid_row_id,
)
from app.services.procurement_notifications import enqueue_procurement_telegram_notifications
from app.services.procurement_scoring import apply_procurement_score


HISTORY_OPERATION_TYPES = ("edit", "fill")


async def undo_grid_history(
    session: AsyncSession,
    *,
    workspace_id: str,
    table_id: str,
    user_id: str | None = None,
    session_id: str | None = None,
) -> GridHistoryMutationResponse:
    if table_id == AUCTION_LOTS_TABLE_ID:
        return await undo_auction_lot_grid_history(
            session,
            workspace_id=workspace_id,
            table_id=table_id,
            user_id=user_id,
            session_id=session_id,
        )
    if table_id != PROCUREMENT_LOTS_TABLE_ID:
        raise ValueError(f"Unsupported history tableId: {table_id}")
    return await _apply_procurement_history(
        session,
        action="undo",
        workspace_id=workspace_id,
        table_id=table_id,
        user_id=user_id,
        session_id=session_id,
    )


async def redo_grid_history(
    session: AsyncSession,
    *,
    workspace_id: str,
    table_id: str,
    user_id: str | None = None,
    session_id: str | None = None,
) -> GridHistoryMutationResponse:
    if table_id == AUCTION_LOTS_TABLE_ID:
        return await redo_auction_lot_grid_history(
            session,
            workspace_id=workspace_id,
            table_id=table_id,
            user_id=user_id,
            session_id=session_id,
        )
    if table_id != PROCUREMENT_LOTS_TABLE_ID:
        raise ValueError(f"Unsupported history tableId: {table_id}")
    return await _apply_procurement_history(
        session,
        action="redo",
        workspace_id=workspace_id,
        table_id=table_id,
        user_id=user_id,
        session_id=session_id,
    )


async def get_grid_history_status(
    session: AsyncSession,
    *,
    workspace_id: str,
    table_id: str,
    user_id: str | None = None,
    session_id: str | None = None,
) -> GridHistoryStatusResponse:
    if table_id == AUCTION_LOTS_TABLE_ID:
        return await get_auction_lot_grid_history_status(
            session,
            workspace_id=workspace_id,
            table_id=table_id,
            user_id=user_id,
            session_id=session_id,
        )
    if table_id != PROCUREMENT_LOTS_TABLE_ID:
        raise ValueError(f"Unsupported history tableId: {table_id}")

    undo_operation = await _find_history_operation(
        session,
        workspace_id=workspace_id,
        table_id=table_id,
        user_id=user_id,
        session_id=session_id,
        action="undo",
        with_for_update=False,
    )
    redo_operation = await _find_history_operation(
        session,
        workspace_id=workspace_id,
        table_id=table_id,
        user_id=user_id,
        session_id=session_id,
        action="redo",
        with_for_update=False,
    )
    return GridHistoryStatusResponse(can_undo=undo_operation is not None, can_redo=redo_operation is not None)


async def _apply_procurement_history(
    session: AsyncSession,
    *,
    action: str,
    workspace_id: str,
    table_id: str,
    user_id: str | None,
    session_id: str | None,
) -> GridHistoryMutationResponse:
    operation = await _find_history_operation(
        session,
        workspace_id=workspace_id,
        table_id=table_id,
        user_id=user_id,
        session_id=session_id,
        action=action,
        with_for_update=True,
    )
    if operation is None:
        version = await get_dataset_version(session, workspace_id, table_id)
        return GridHistoryMutationResponse(dataset_version=version, updated_rows=[])

    service = ProcurementGridHistoryService(workspace_id=workspace_id)
    try:
        result = await service.apply_loaded_operation(session, operation, action)  # type: ignore[arg-type]
    except ApiException as error:
        if error.status_code == 404:
            raise LookupError(error.message) from error
        raise ValueError(error.message) from error

    dataset_version = int(result.revision)
    changed_fields_by_row = await _operation_changed_fields(session, operation.id, workspace_id=workspace_id, table_id=table_id)
    for record in result.rows:
        row_id = procurement_lot_grid_row_id(record)
        await enqueue_procurement_telegram_notifications(session, record)
        session.add(
            GridChangeEventModel(
                workspace_id=workspace_id,
                table_id=table_id,
                dataset_version=dataset_version,
                event_type="row_updated",
                row_id=row_id,
                payload={
                    "source": f"grid_history_{action}",
                    "operation_id": str(operation.id),
                    "changed_fields": sorted(changed_fields_by_row.get(row_id, set())),
                },
            )
        )
    await session.flush()

    return GridHistoryMutationResponse(
        dataset_version=dataset_version,
        updated_rows=[
            ProcurementLotsGridPullRow(
                id=procurement_lot_grid_row_id(record),
                index=int(record.id or 0),
                row=build_procurement_grid_row(record),
            )
            for record in result.rows
        ],
    )


async def _find_history_operation(
    session: AsyncSession,
    *,
    workspace_id: str,
    table_id: str,
    user_id: str | None,
    session_id: str | None,
    action: str,
    with_for_update: bool,
) -> GridOperationModel | None:
    statement = select(GridOperationModel).where(
        GridOperationModel.workspace_id == workspace_id,
        GridOperationModel.table_id == table_id,
        GridOperationModel.operation_type.in_(HISTORY_OPERATION_TYPES),
    )
    if user_id is None:
        statement = statement.where(GridOperationModel.user_id.is_(None))
    else:
        statement = statement.where(GridOperationModel.user_id == user_id)
    if session_id is None:
        statement = statement.where(GridOperationModel.session_id.is_(None))
    else:
        statement = statement.where(GridOperationModel.session_id == session_id)

    if action == "undo":
        statement = statement.where(GridOperationModel.undone_at.is_(None)).order_by(GridOperationModel.created_at.desc())
    elif action == "redo":
        statement = statement.where(GridOperationModel.undone_at.is_not(None)).order_by(
            GridOperationModel.undone_at.desc(),
            GridOperationModel.created_at.desc(),
        )
    else:
        raise ValueError(f"Unsupported history action: {action}")
    if with_for_update:
        statement = statement.with_for_update()
    return await session.scalar(statement.limit(1))


async def _operation_changed_fields(
    session: AsyncSession,
    operation_id: UUID,
    *,
    workspace_id: str,
    table_id: str,
) -> dict[str, set[str]]:
    events = (
        await session.scalars(
            select(GridCellEventModel)
            .where(
                GridCellEventModel.operation_id == operation_id,
                GridCellEventModel.workspace_id == workspace_id,
                GridCellEventModel.table_id == table_id,
            )
            .order_by(GridCellEventModel.id)
        )
    ).all()
    changed_fields: dict[str, set[str]] = {}
    for event in events:
        try:
            field_name = _field_for_column(event.column_id)
        except ValueError:
            field_name = event.column_id
        changed_fields.setdefault(event.row_id, set()).add(field_name)
    return changed_fields


class ProcurementGridRevisionService:
    def __init__(self, *, workspace_id: str) -> None:
        self.workspace_id = workspace_id

    async def get_revision(self, session: AsyncSession) -> str:
        return str(await get_dataset_version(session, self.workspace_id, PROCUREMENT_LOTS_TABLE_ID))

    async def bump_revision(self, session: AsyncSession) -> str:
        return str(await bump_procurement_lot_dataset_version(session, workspace_id=self.workspace_id))


class ProcurementGridHistoryService(GridHistoryServiceBase):
    def __init__(self, *, workspace_id: str) -> None:
        super().__init__(
            _procurement_table_definition(),
            ProcurementGridRevisionService(workspace_id=workspace_id),  # type: ignore[arg-type]
        )

    async def get_operation(
        self,
        session: AsyncSession,
        operation_id: str,
        *,
        with_for_update: bool = False,
    ) -> GridOperationModel | None:
        try:
            operation_uuid = UUID(str(operation_id))
        except ValueError:
            return None
        statement = select(GridOperationModel).where(GridOperationModel.id == operation_uuid)
        if with_for_update:
            statement = statement.with_for_update()
        return await session.scalar(statement)

    def get_operation_id(self, operation: GridOperationModel) -> str:
        return str(operation.id)

    def get_operation_type(self, operation: GridOperationModel) -> str:
        return operation.operation_type

    def get_operation_status(self, operation: GridOperationModel) -> str:
        return "undone" if operation.undone_at is not None else "applied"

    def set_operation_status(self, operation: GridOperationModel, status: str) -> None:
        if status == "undone":
            operation.undone_at = datetime.now(UTC)
            return
        if status == "applied":
            operation.undone_at = None
            return
        raise ValueError(f"Unsupported operation status: {status}")

    def set_operation_modified_at(self, operation: GridOperationModel, changed_at: datetime) -> None:
        if operation.undone_at is not None:
            operation.undone_at = changed_at

    def set_operation_revision(self, operation: GridOperationModel, changed_at: datetime) -> None:
        del changed_at

    async def load_cell_events(
        self,
        session: AsyncSession,
        operation_id: str,
        *,
        workspace_id: str | None = None,
        table_id: str | None = None,
        force_unscoped: bool = False,
    ) -> list[GridCellEventModel]:
        del force_unscoped
        try:
            operation_uuid = UUID(str(operation_id))
        except ValueError:
            return []
        statement = select(GridCellEventModel).where(GridCellEventModel.operation_id == operation_uuid)
        if workspace_id is not None:
            statement = statement.where(GridCellEventModel.workspace_id == workspace_id)
        if table_id is not None:
            statement = statement.where(GridCellEventModel.table_id == table_id)
        return list((await session.scalars(statement.order_by(GridCellEventModel.id))).all())

    async def fetch_rows_by_ids(
        self,
        session: AsyncSession,
        row_ids: list[str],
        *,
        with_for_update: bool = False,
        workspace_id: str | None = None,
        table_id: str | None = None,
        force_unscoped: bool = False,
    ) -> dict[str, ProcurementLotRecord]:
        del workspace_id, table_id, force_unscoped
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

    def event_row_id(self, event: GridCellEventModel) -> str:
        return event.row_id

    def event_column_id(self, event: GridCellEventModel) -> str:
        return event.column_id

    def event_before_value(self, event: GridCellEventModel) -> Any:
        return _event_wrapped_value(event.before_value)

    def event_after_value(self, event: GridCellEventModel) -> Any:
        return _event_wrapped_value(event.after_value)

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

    def set_row_updated_at(self, row: ProcurementLotRecord, changed_at: datetime) -> None:
        row.updated_at = changed_at

    def get_row_id(self, row: ProcurementLotRecord) -> str:
        return procurement_lot_grid_row_id(row)

    def get_row_index(self, row: ProcurementLotRecord) -> int:
        return int(row.id or 0)

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


def _event_wrapped_value(payload: Any) -> Any:
    if isinstance(payload, dict) and "value" in payload:
        return payload.get("value")
    return payload


def _field_for_column(column_id: str) -> str:
    calculator_field = calculator_field_for_column(column_id)
    if calculator_field is not None:
        return calculator_field
    return _procurement_field_for_column(column_id)


def _procurement_table_definition() -> GridTableDefinition:
    columns = {
        column_id: GridColumnDefinition(
            id=column_id,
            model_attr=field_name,
            editable=True,
            value_type="string",
        )
        for column_id, field_name in PROCUREMENT_EDIT_COLUMNS.items()
    }
    for column_id, calculator_field in CALCULATOR_INPUT_COLUMNS.items():
        columns[column_id] = GridColumnDefinition(
            id=column_id,
            model_attr=calculator_field,
            editable=True,
            value_type="string",
        )
    return GridTableDefinition(
        table_id=PROCUREMENT_LOTS_TABLE_ID,
        model=ProcurementLotRecord,
        row_id_attr="external_id",
        row_index_attr="id",
        updated_at_attr="updated_at",
        columns=columns,
    )
