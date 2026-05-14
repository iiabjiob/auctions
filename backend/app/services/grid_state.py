from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.grid import GridCellEventModel, GridChangeEventModel, GridOperationModel, GridRevisionModel


def _require_scope_value(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _json_payload(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    return dict(payload or {})


async def get_or_create_grid_revision(
    session: AsyncSession,
    workspace_id: str,
    table_id: str,
) -> GridRevisionModel:
    workspace_id = _require_scope_value(workspace_id, "workspace_id")
    table_id = _require_scope_value(table_id, "table_id")

    insert_statement = (
        pg_insert(GridRevisionModel)
        .values(workspace_id=workspace_id, table_id=table_id, dataset_version=0)
        .on_conflict_do_nothing(index_elements=["workspace_id", "table_id"])
    )
    await session.execute(insert_statement)

    revision = await session.scalar(
        select(GridRevisionModel)
        .where(GridRevisionModel.workspace_id == workspace_id, GridRevisionModel.table_id == table_id)
        .with_for_update()
    )
    if revision is None:
        raise RuntimeError(f"Grid revision was not created for {workspace_id}/{table_id}")
    return revision


async def get_dataset_version(session: AsyncSession, workspace_id: str, table_id: str) -> int:
    revision = await get_or_create_grid_revision(session, workspace_id, table_id)
    return int(revision.dataset_version)


async def bump_dataset_version(
    session: AsyncSession,
    workspace_id: str,
    table_id: str,
    *,
    event_type: str | None = None,
    row_id: str | None = None,
    payload: Mapping[str, Any] | None = None,
) -> int:
    revision = await get_or_create_grid_revision(session, workspace_id, table_id)
    revision.dataset_version = int(revision.dataset_version) + 1
    revision.updated_at = datetime.now(UTC)

    if event_type is not None:
        normalized_event_type = _require_scope_value(event_type, "event_type")
        session.add(
            GridChangeEventModel(
                workspace_id=revision.workspace_id,
                table_id=revision.table_id,
                dataset_version=revision.dataset_version,
                event_type=normalized_event_type,
                row_id=row_id,
                payload=_json_payload(payload),
            )
        )

    await session.flush()
    return int(revision.dataset_version)


async def record_grid_operation(
    session: AsyncSession,
    *,
    workspace_id: str,
    table_id: str,
    operation_type: str,
    user_id: str | None = None,
    session_id: str | None = None,
    base_version: int | None = None,
    resulting_version: int | None = None,
    payload: Mapping[str, Any] | None = None,
    undo_payload: Mapping[str, Any] | None = None,
    redo_payload: Mapping[str, Any] | None = None,
) -> GridOperationModel:
    operation = GridOperationModel(
        workspace_id=_require_scope_value(workspace_id, "workspace_id"),
        table_id=_require_scope_value(table_id, "table_id"),
        user_id=user_id,
        session_id=session_id,
        operation_type=_require_scope_value(operation_type, "operation_type"),
        base_version=base_version,
        resulting_version=resulting_version,
        payload=_json_payload(payload),
        undo_payload=dict(undo_payload) if undo_payload is not None else None,
        redo_payload=dict(redo_payload) if redo_payload is not None else None,
    )
    session.add(operation)
    await session.flush()
    return operation


async def record_grid_cell_events_from_payloads(
    session: AsyncSession,
    *,
    operation_id: UUID,
    workspace_id: str,
    table_id: str,
    undo_payload: Mapping[str, Any] | None,
    redo_payload: Mapping[str, Any] | None,
) -> list[GridCellEventModel]:
    before_by_key = _payload_values_by_cell(undo_payload)
    after_by_key = _payload_values_by_cell(redo_payload)
    events: list[GridCellEventModel] = []
    for key in sorted(set(before_by_key) | set(after_by_key)):
        row_id, column_id = key
        event = GridCellEventModel(
            operation_id=operation_id,
            workspace_id=_require_scope_value(workspace_id, "workspace_id"),
            table_id=_require_scope_value(table_id, "table_id"),
            row_id=row_id,
            column_id=column_id,
            before_value={"value": before_by_key.get(key)},
            after_value={"value": after_by_key.get(key)},
        )
        session.add(event)
        events.append(event)
    await session.flush()
    return events


def _payload_values_by_cell(payload: Mapping[str, Any] | None) -> dict[tuple[str, str], Any]:
    values: dict[tuple[str, str], Any] = {}
    edits = payload.get("edits") if isinstance(payload, Mapping) else None
    if not isinstance(edits, list):
        return values
    for edit in edits:
        if not isinstance(edit, Mapping):
            continue
        row_id = edit.get("rowId")
        column_id = edit.get("columnId")
        if not isinstance(row_id, str) or not row_id.strip() or not isinstance(column_id, str) or not column_id.strip():
            continue
        values[(row_id.strip(), column_id.strip())] = edit.get("value")
    return values


async def clear_redo_grid_operations(
    session: AsyncSession,
    *,
    workspace_id: str,
    table_id: str,
    user_id: str | None = None,
    session_id: str | None = None,
) -> int:
    statement = delete(GridOperationModel).where(
        GridOperationModel.workspace_id == _require_scope_value(workspace_id, "workspace_id"),
        GridOperationModel.table_id == _require_scope_value(table_id, "table_id"),
        GridOperationModel.undone_at.is_not(None),
    )
    if user_id is None:
        statement = statement.where(GridOperationModel.user_id.is_(None))
    else:
        statement = statement.where(GridOperationModel.user_id == user_id)
    if session_id is None:
        statement = statement.where(GridOperationModel.session_id.is_(None))
    else:
        statement = statement.where(GridOperationModel.session_id == session_id)

    result = await session.execute(statement)
    return int(result.rowcount or 0)
