from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auction import AuctionLotDetailCache, AuctionLotRecord
from app.models.grid import GridChangeEventModel, GridOperationModel
from app.schemas.auction_grid import AuctionLotsGridPullRow
from app.schemas.grid_history import GridHistoryMutationResponse, GridHistoryStatusResponse
from app.services.auction_analysis_config import auction_analysis_config_service
from app.services.auction_datagrid_payload import validate_datagrid_row_payload
from app.services.auction_grid_edits import WORKSPACE_EDIT_COLUMNS, _coerce_value, _find_record_by_row_id, _workspace_field_for_column
from app.services.auction_grid_state import AUCTION_LOTS_TABLE_ID, DEFAULT_GRID_WORKSPACE_ID
from app.services.auction_scoring import (
    recalculate_record_rating,
    sync_record_from_detail_cache,
)
from app.services.auction_search import update_record_search_text
from app.services.auction_workspace import ensure_work_item
from app.services.lot_decision_report import generate_and_persist_lot_decision_report_snapshot
from app.services.grid_state import bump_dataset_version, get_dataset_version


@dataclass(frozen=True)
class GridHistoryScope:
    workspace_id: str
    table_id: str
    user_id: str | None = None
    session_id: str | None = None


WORKSPACE_EDIT_FIELD_NAMES = set(WORKSPACE_EDIT_COLUMNS.values())


async def undo_auction_lot_grid_history(
    session: AsyncSession,
    *,
    workspace_id: str = DEFAULT_GRID_WORKSPACE_ID,
    table_id: str = AUCTION_LOTS_TABLE_ID,
    user_id: str | None = None,
    session_id: str | None = None,
) -> GridHistoryMutationResponse:
    scope = _build_scope(workspace_id=workspace_id, table_id=table_id, user_id=user_id, session_id=session_id)
    operation = await _find_history_operation(session, scope, undone=False)
    if operation is None:
        return await _empty_history_response(session, scope)
    response = await _apply_history_payload(session, operation, scope=scope, payload_key="undo_payload", event_source="history_undo")
    operation.undone_at = datetime.now(UTC)
    await session.flush()
    return response


async def redo_auction_lot_grid_history(
    session: AsyncSession,
    *,
    workspace_id: str = DEFAULT_GRID_WORKSPACE_ID,
    table_id: str = AUCTION_LOTS_TABLE_ID,
    user_id: str | None = None,
    session_id: str | None = None,
) -> GridHistoryMutationResponse:
    scope = _build_scope(workspace_id=workspace_id, table_id=table_id, user_id=user_id, session_id=session_id)
    operation = await _find_history_operation(session, scope, undone=True)
    if operation is None:
        return await _empty_history_response(session, scope)
    response = await _apply_history_payload(session, operation, scope=scope, payload_key="redo_payload", event_source="history_redo")
    operation.undone_at = None
    await session.flush()
    return response


async def get_auction_lot_grid_history_status(
    session: AsyncSession,
    *,
    workspace_id: str = DEFAULT_GRID_WORKSPACE_ID,
    table_id: str = AUCTION_LOTS_TABLE_ID,
    user_id: str | None = None,
    session_id: str | None = None,
) -> GridHistoryStatusResponse:
    scope = _build_scope(workspace_id=workspace_id, table_id=table_id, user_id=user_id, session_id=session_id)
    return GridHistoryStatusResponse(
        can_undo=await _has_history_operation(session, scope, undone=False),
        can_redo=await _has_history_operation(session, scope, undone=True),
    )


def _build_scope(*, workspace_id: str, table_id: str, user_id: str | None, session_id: str | None) -> GridHistoryScope:
    workspace_id = _normalize_required_scope_value(workspace_id, "workspace_id")
    table_id = _normalize_required_scope_value(table_id, "table_id")
    if table_id != AUCTION_LOTS_TABLE_ID:
        raise ValueError("Only auction-lots history is supported")
    return GridHistoryScope(
        workspace_id=workspace_id,
        table_id=table_id,
        user_id=_normalize_optional_scope_value(user_id),
        session_id=_normalize_optional_scope_value(session_id),
    )


async def _empty_history_response(session: AsyncSession, scope: GridHistoryScope) -> GridHistoryMutationResponse:
    return GridHistoryMutationResponse(
        dataset_version=await get_dataset_version(session, scope.workspace_id, scope.table_id),
        updated_rows=[],
    )


async def _find_history_operation(
    session: AsyncSession,
    scope: GridHistoryScope,
    *,
    undone: bool,
) -> GridOperationModel | None:
    statement = (
        select(GridOperationModel)
        .where(
            *_history_scope_predicates(scope),
            GridOperationModel.operation_type == "edit",
        )
        .with_for_update()
        .limit(1)
    )
    if undone:
        statement = statement.where(GridOperationModel.undone_at.is_not(None)).order_by(
            GridOperationModel.undone_at.desc(),
            GridOperationModel.created_at.desc(),
        )
    else:
        statement = statement.where(GridOperationModel.undone_at.is_(None)).order_by(GridOperationModel.created_at.desc())
    return await session.scalar(statement)


async def _has_history_operation(session: AsyncSession, scope: GridHistoryScope, *, undone: bool) -> bool:
    statement = (
        select(GridOperationModel.id)
        .where(
            *_history_scope_predicates(scope),
            GridOperationModel.operation_type == "edit",
        )
        .limit(1)
    )
    if undone:
        statement = statement.where(GridOperationModel.undone_at.is_not(None))
    else:
        statement = statement.where(GridOperationModel.undone_at.is_(None))
    return (await session.scalar(statement)) is not None


def _history_scope_predicates(scope: GridHistoryScope) -> tuple[Any, ...]:
    predicates: list[Any] = [
        GridOperationModel.workspace_id == scope.workspace_id,
        GridOperationModel.table_id == scope.table_id,
    ]
    if scope.user_id is None:
        predicates.append(GridOperationModel.user_id.is_(None))
    else:
        predicates.append(GridOperationModel.user_id == scope.user_id)
    if scope.session_id is None:
        predicates.append(GridOperationModel.session_id.is_(None))
    else:
        predicates.append(GridOperationModel.session_id == scope.session_id)
    return tuple(predicates)


async def _apply_history_payload(
    session: AsyncSession,
    operation: GridOperationModel,
    *,
    scope: GridHistoryScope,
    payload_key: str,
    event_source: str,
) -> GridHistoryMutationResponse:
    history_edits = _history_payload_edits(getattr(operation, payload_key, None))
    if not history_edits:
        raise ValueError(f"Grid operation {operation.id} has no {payload_key}.edits payload")

    edits_by_row: dict[str, list[dict[str, Any]]] = {}
    row_order: list[str] = []
    for edit in history_edits:
        row_id = _history_edit_row_id(edit)
        if row_id not in edits_by_row:
            row_order.append(row_id)
            edits_by_row[row_id] = []
        edits_by_row[row_id].append(edit)

    runtime_config = await auction_analysis_config_service.get_runtime_config(session)
    updated_records: dict[str, AuctionLotRecord] = {}
    changed_fields_by_row: dict[str, set[str]] = {}

    for row_id in row_order:
        record = await _find_record_by_row_id(session, row_id)
        if record is None:
            raise LookupError(f"Lot row was not found for rowId={row_id}")

        detail_cache = await session.scalar(
            select(AuctionLotDetailCache).where(AuctionLotDetailCache.lot_record_id == record.id)
        )
        if detail_cache is not None:
            sync_record_from_detail_cache(record, detail_cache)
        work_item = await ensure_work_item(session, record)
        changed_fields_by_row.setdefault(row_id, set())

        for edit in edits_by_row[row_id]:
            field_name = _history_edit_field(edit)
            setattr(work_item, field_name, _coerce_value(field_name, edit.get("value")))
            changed_fields_by_row[row_id].add(field_name)

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
        update_record_search_text(record)
        await generate_and_persist_lot_decision_report_snapshot(session, record, detail_cache, work_item)
        updated_records[row_id] = record

    dataset_version = await bump_dataset_version(session, scope.workspace_id, scope.table_id)
    for row_id, changed_fields in changed_fields_by_row.items():
        session.add(
            GridChangeEventModel(
                workspace_id=scope.workspace_id,
                table_id=scope.table_id,
                dataset_version=dataset_version,
                event_type="row_updated",
                row_id=row_id,
                payload={
                    "source": event_source,
                    "operation_id": str(operation.id),
                    "changed_fields": sorted(changed_fields),
                },
            )
        )
    await session.flush()

    return GridHistoryMutationResponse(
        dataset_version=dataset_version,
        updated_rows=[
            AuctionLotsGridPullRow(
                id=row_id,
                index=int(record.id),
                row=validate_datagrid_row_payload(record.datagrid_row),
            )
            for row_id, record in updated_records.items()
        ],
    )


def _history_payload_edits(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    edits = payload.get("edits")
    if not isinstance(edits, list):
        return []
    return [edit for edit in edits if isinstance(edit, dict)]


def _history_edit_row_id(edit: dict[str, Any]) -> str:
    value = edit.get("rowId")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("History edit rowId is required")
    return value.strip()


def _history_edit_field(edit: dict[str, Any]) -> str:
    field_name = edit.get("field")
    if isinstance(field_name, str) and field_name in WORKSPACE_EDIT_FIELD_NAMES:
        return field_name

    column_id = edit.get("columnId")
    if isinstance(column_id, str) and column_id.strip():
        return _workspace_field_for_column(column_id.strip())
    raise ValueError("History edit field or columnId is required")


def _normalize_required_scope_value(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _normalize_optional_scope_value(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None
