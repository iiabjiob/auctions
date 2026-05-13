from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.grid import GridChangeEventModel
from app.models.procurement import ProcurementLotRecord, _sync_procurement_lot_search_text
from app.schemas.procurement_grid import (
    ProcurementLotsGridCellEdit,
    ProcurementLotsGridEditRequest,
    ProcurementLotsGridEditResponse,
    ProcurementLotsGridPullRow,
)
from app.services.grid_state import clear_redo_grid_operations, get_or_create_grid_revision, record_grid_operation
from app.services.procurement_calculator import (
    calculator_field_for_column,
    coerce_calculator_input_value,
    recalculate_procurement_lot,
)
from app.services.procurement_grid import build_procurement_grid_row
from app.services.procurement_grid_state import (
    DEFAULT_GRID_WORKSPACE_ID,
    PROCUREMENT_LOTS_TABLE_ID,
    bump_procurement_lot_dataset_version,
    procurement_lot_grid_row_id,
)
from app.services.procurement_notifications import enqueue_procurement_telegram_notifications
from app.services.procurement_scoring import apply_procurement_score


class ProcurementGridEditConflictError(Exception):
    def __init__(self, *, base_version: int, current_version: int) -> None:
        self.base_version = base_version
        self.current_version = current_version
        super().__init__(f"Grid dataset version conflict: baseVersion={base_version}, current={current_version}")


@dataclass(frozen=True)
class PreparedProcurementGridEdit:
    row_id: str
    column_id: str
    field_name: str
    value: Any
    target: str = "record"


DECIMAL_EDIT_FIELDS = {
    "bid_security_amount",
    "contract_security_amount",
    "prepayment_percent",
    "quantity",
    "unit_nmck",
}
BOOLEAN_EDIT_FIELDS = {"documentation_present"}
CALCULATION_TRIGGER_RECORD_FIELDS = {
    "bid_security_amount",
    "contract_security_amount",
    "prepayment_percent",
    "quantity",
    "unit_nmck",
}
TEXT_EDIT_FIELDS = {
    "assignee",
    "certificate_requirements",
    "comment",
    "final_decision",
    "payment_terms",
    "rejection_reason",
}
WORKFLOW_STATUS_ALIASES = {
    "new": "new",
    "новый": "new",
    "quick_filter": "quick_filter",
    "quickFilter": "quick_filter",
    "быстрый фильтр": "quick_filter",
    "calculating": "calculating",
    "считаем": "calculating",
    "questions": "questions",
    "вопросы по тз": "questions",
    "production_check": "production_check",
    "productionCheck": "production_check",
    "проверка цеха": "production_check",
    "decision": "decision",
    "на решение": "decision",
    "submitting": "submitting",
    "подаем": "submitting",
    "подаём": "submitting",
    "submitted": "submitted",
    "подано": "submitted",
    "auction": "auction",
    "аукцион": "auction",
    "won": "won",
    "выиграли": "won",
    "lost": "lost",
    "проиграли": "lost",
    "rejected": "rejected",
    "отказ": "rejected",
}

PROCUREMENT_EDIT_COLUMNS = {
    "workflowStatus": "workflow_status",
    "assignee": "assignee",
    "comment": "comment",
    "finalDecision": "final_decision",
    "rejectionReason": "rejection_reason",
    "bidSecurityAmount": "bid_security_amount",
    "certificateRequirements": "certificate_requirements",
    "contractSecurityAmount": "contract_security_amount",
    "documentationPresent": "documentation_present",
    "paymentTerms": "payment_terms",
    "prepaymentPercent": "prepayment_percent",
    "quantity": "quantity",
    "unitNmck": "unit_nmck",
}
PROCUREMENT_EDIT_COLUMNS.update({field_name: field_name for field_name in set(PROCUREMENT_EDIT_COLUMNS.values())})


async def commit_procurement_lot_grid_edits(
    session: AsyncSession,
    request: ProcurementLotsGridEditRequest,
    *,
    workspace_id: str = DEFAULT_GRID_WORKSPACE_ID,
    user_id: str | None = None,
    session_id: str | None = None,
) -> ProcurementLotsGridEditResponse:
    prepared_edits = [_prepare_edit(edit) for edit in request.edits]
    edits_by_row: dict[str, list[PreparedProcurementGridEdit]] = defaultdict(list)
    row_order: list[str] = []
    for edit in prepared_edits:
        if edit.row_id not in edits_by_row:
            row_order.append(edit.row_id)
        edits_by_row[edit.row_id].append(edit)

    revision = await get_or_create_grid_revision(session, workspace_id, PROCUREMENT_LOTS_TABLE_ID)
    current_version = int(revision.dataset_version)
    if current_version != request.base_version:
        raise ProcurementGridEditConflictError(base_version=request.base_version, current_version=current_version)

    updated_records: dict[str, ProcurementLotRecord] = {}
    changed_fields_by_row: dict[str, set[str]] = {}
    undo_values: dict[tuple[str, str], dict[str, Any]] = {}
    redo_values: dict[tuple[str, str], dict[str, Any]] = {}

    for requested_row_id in row_order:
        record = await _find_record_by_row_id(session, requested_row_id)
        if record is None:
            raise LookupError(f"Procurement lot row was not found for rowId={requested_row_id}")

        stable_row_id = procurement_lot_grid_row_id(record)
        changed_fields_by_row.setdefault(stable_row_id, set())
        should_recalculate = False

        for edit in edits_by_row[requested_row_id]:
            key = (stable_row_id, edit.field_name)
            if key not in undo_values:
                old_value = (
                    _calculator_input_value(record, edit.field_name)
                    if edit.target == "calculator"
                    else getattr(record, edit.field_name)
                )
                undo_values[key] = {
                    "rowId": stable_row_id,
                    "columnId": edit.column_id,
                    "field": edit.field_name,
                    "target": edit.target,
                    "value": _json_value(old_value),
                }
            if edit.target == "calculator":
                _set_calculator_input_value(record, edit.field_name, edit.value)
            else:
                setattr(record, edit.field_name, edit.value)
            should_recalculate = should_recalculate or (
                edit.target == "calculator" or edit.field_name in CALCULATION_TRIGGER_RECORD_FIELDS
            )
            redo_values[key] = {
                "rowId": stable_row_id,
                "columnId": edit.column_id,
                "field": edit.field_name,
                "target": edit.target,
                "value": _json_value(edit.value),
            }
            changed_fields_by_row[stable_row_id].add(edit.field_name)

        if should_recalculate:
            recalculate_procurement_lot(record)
        apply_procurement_score(record)
        await enqueue_procurement_telegram_notifications(session, record)
        _sync_procurement_lot_search_text(None, None, record)
        updated_records[stable_row_id] = record

    resulting_version = await bump_procurement_lot_dataset_version(session, workspace_id=workspace_id)
    for row_id, changed_fields in changed_fields_by_row.items():
        session.add(
            GridChangeEventModel(
                workspace_id=workspace_id,
                table_id=PROCUREMENT_LOTS_TABLE_ID,
                dataset_version=resulting_version,
                event_type="row_updated",
                row_id=row_id,
                payload={"source": "grid_edit", "changed_fields": sorted(changed_fields)},
            )
        )

    await clear_redo_grid_operations(
        session,
        workspace_id=workspace_id,
        table_id=PROCUREMENT_LOTS_TABLE_ID,
        user_id=user_id,
        session_id=session_id,
    )
    await record_grid_operation(
        session,
        workspace_id=workspace_id,
        table_id=PROCUREMENT_LOTS_TABLE_ID,
        operation_type="edit",
        user_id=user_id,
        session_id=session_id,
        base_version=request.base_version,
        resulting_version=resulting_version,
        payload={"edits": [edit.model_dump(by_alias=True, mode="json") for edit in request.edits]},
        undo_payload={"edits": list(undo_values.values())},
        redo_payload={"edits": list(redo_values.values())},
    )
    await session.flush()

    return ProcurementLotsGridEditResponse(
        dataset_version=resulting_version,
        updated_rows=[
            ProcurementLotsGridPullRow(
                id=row_id,
                index=int(record.id or 0),
                row=build_procurement_grid_row(record),
            )
            for row_id, record in updated_records.items()
        ],
    )


async def _find_record_by_row_id(session: AsyncSession, row_id: str) -> ProcurementLotRecord | None:
    source, external_id = _parse_row_id(row_id)
    return await session.scalar(
        select(ProcurementLotRecord)
        .where(ProcurementLotRecord.source_code == source, ProcurementLotRecord.external_id == external_id)
        .with_for_update()
    )


def _parse_row_id(row_id: str) -> tuple[str, str]:
    parts = row_id.split(":", 1)
    if len(parts) != 2 or not all(part.strip() for part in parts):
        raise ValueError("rowId must use the stable source:externalId format")
    source, external_id = parts
    return source.strip(), external_id.strip()


def _prepare_edit(edit: ProcurementLotsGridCellEdit) -> PreparedProcurementGridEdit:
    calculator_field = calculator_field_for_column(edit.column_id)
    if calculator_field is not None:
        return PreparedProcurementGridEdit(
            row_id=edit.row_id,
            column_id=edit.column_id,
            field_name=calculator_field,
            value=coerce_calculator_input_value(calculator_field, edit.value),
            target="calculator",
        )
    field_name = _procurement_field_for_column(edit.column_id)
    return PreparedProcurementGridEdit(
        row_id=edit.row_id,
        column_id=edit.column_id,
        field_name=field_name,
        value=_coerce_value(field_name, edit.value),
    )


def _calculator_input_value(record: ProcurementLotRecord, field_name: str) -> Any:
    return dict(record.calculator_inputs or {}).get(field_name)


def _set_calculator_input_value(record: ProcurementLotRecord, field_name: str, value: Any) -> None:
    inputs = dict(record.calculator_inputs or {})
    if value is None:
        inputs.pop(field_name, None)
    else:
        inputs[field_name] = value
    record.calculator_inputs = inputs


def _procurement_field_for_column(column_id: str) -> str:
    field_name = PROCUREMENT_EDIT_COLUMNS.get(column_id)
    if field_name is None:
        raise ValueError(f"Column is not editable: {column_id}")
    return field_name


def _coerce_value(field_name: str, value: Any) -> Any:
    if field_name == "workflow_status":
        return _coerce_workflow_status(value)
    if field_name in DECIMAL_EDIT_FIELDS:
        return _coerce_decimal(value, field_name)
    if field_name in BOOLEAN_EDIT_FIELDS:
        return _coerce_boolean(value, field_name)
    if field_name in TEXT_EDIT_FIELDS:
        return _coerce_nullable_text(value, field_name)
    raise ValueError(f"Field is not editable: {field_name}")


def _coerce_workflow_status(value: Any) -> str:
    if value is None:
        raise ValueError("workflow_status must not be empty")
    if not isinstance(value, str):
        raise ValueError("workflow_status must be text")
    normalized = value.strip()
    if not normalized:
        raise ValueError("workflow_status must not be empty")
    status = WORKFLOW_STATUS_ALIASES.get(normalized) or WORKFLOW_STATUS_ALIASES.get(normalized.lower())
    if status is None:
        allowed = ", ".join(sorted(set(WORKFLOW_STATUS_ALIASES.values())))
        raise ValueError(f"workflow_status must be one of: {allowed}")
    return status


def _coerce_decimal(value: Any, field_name: str) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip().replace(" ", "").replace(",", ".")
        if not normalized:
            return None
    elif isinstance(value, Decimal):
        normalized = str(value)
    elif isinstance(value, bool):
        raise ValueError(f"{field_name} must be a number")
    elif isinstance(value, int | float):
        normalized = str(value)
    else:
        raise ValueError(f"{field_name} must be a number")

    try:
        return Decimal(normalized)
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"{field_name} must be a number") from error


def _coerce_boolean(value: Any, field_name: str) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"", "null"}:
            return None
        if normalized in {"false", "0", "no", "off"}:
            return False
        if normalized in {"true", "1", "yes", "on"}:
            return True
    raise ValueError(f"{field_name} must be a boolean")


def _coerce_nullable_text(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict | list):
        raise ValueError(f"{field_name} must be text")
    normalized = str(value).strip()
    return normalized or None


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value
