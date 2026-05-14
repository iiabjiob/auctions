from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auction import AuctionLotRecord
from app.schemas.auction_grid import (
    AuctionLotsGridCellEdit,
    AuctionLotsGridEditRequest,
    AuctionLotsGridEditResponse,
    AuctionLotsGridPullRow,
)
from app.services.auction_datagrid_payload import validate_datagrid_row_payload
from app.services.auction_grid_state import AUCTION_LOTS_TABLE_ID, DEFAULT_GRID_WORKSPACE_ID, auction_lot_grid_row_id


class AuctionGridEditConflictError(Exception):
    def __init__(self, *, base_version: int, current_version: int) -> None:
        self.base_version = base_version
        self.current_version = current_version
        super().__init__(f"Grid dataset version conflict: baseVersion={base_version}, current={current_version}")


@dataclass(frozen=True)
class PreparedGridEdit:
    row_id: str
    column_id: str
    field_name: str
    value: Any


DECIMAL_EDIT_FIELDS = {
    "max_purchase_price",
    "market_value",
    "platform_fee",
    "delivery_cost",
    "dismantling_cost",
    "repair_cost",
    "storage_cost",
    "legal_cost",
    "other_costs",
    "target_profit",
}

BOOLEAN_EDIT_FIELDS = {"exclude_from_analysis"}
DATETIME_EDIT_FIELDS = {"inspection_at"}

WORKSPACE_EDIT_COLUMNS = {
    "decisionStatus": "decision_status",
    "workDecisionStatus": "decision_status",
    "assignee": "assignee",
    "comment": "comment",
    "inspectionAt": "inspection_at",
    "inspectionResult": "inspection_result",
    "finalDecision": "final_decision",
    "investor": "investor",
    "depositStatus": "deposit_status",
    "applicationStatus": "application_status",
    "excludeFromAnalysis": "exclude_from_analysis",
    "exclusionReason": "exclusion_reason",
    "categoryOverride": "category_override",
    "maxPurchasePrice": "max_purchase_price",
    "marketValue": "market_value",
    "platformFee": "platform_fee",
    "deliveryCost": "delivery_cost",
    "dismantlingCost": "dismantling_cost",
    "repairCost": "repair_cost",
    "storageCost": "storage_cost",
    "legalCost": "legal_cost",
    "otherCosts": "other_costs",
    "targetProfit": "target_profit",
}
WORKSPACE_EDIT_COLUMNS.update({field_name: field_name for field_name in set(WORKSPACE_EDIT_COLUMNS.values())})


async def commit_auction_lot_grid_edits(
    session: AsyncSession,
    request: AuctionLotsGridEditRequest,
    *,
    workspace_id: str = DEFAULT_GRID_WORKSPACE_ID,
    user_id: str | None = None,
    session_id: str | None = None,
) -> AuctionLotsGridEditResponse:
    from app.services.grid_state import get_dataset_version

    base_version = request.base_version
    if base_version is None:
        base_version = await get_dataset_version(session, workspace_id, AUCTION_LOTS_TABLE_ID)
    return await _commit_auction_lot_grid_operations(
        session,
        base_version=base_version,
        edits=request.edits,
        workspace_id=workspace_id,
        user_id=user_id,
        session_id=session_id,
        operation_type="edit",
        payload={"edits": [edit.model_dump(by_alias=True, mode="json") for edit in request.edits]},
    )


async def _commit_auction_lot_grid_operations(
    session: AsyncSession,
    *,
    base_version: int,
    edits: list[AuctionLotsGridCellEdit],
    workspace_id: str = DEFAULT_GRID_WORKSPACE_ID,
    user_id: str | None = None,
    session_id: str | None = None,
    operation_type: str,
    payload: dict[str, Any] | None,
) -> AuctionLotsGridEditResponse:
    from affino_grid_backend import ApiException

    from app.services.grid_backend_edits import AuctionGridEditService, auction_backend_edit_request
    from app.services.grid_backend_transactions import (
        prepare_session_for_package_transaction,
        refresh_package_grid_row,
        run_package_grid_mutation,
    )
    from app.services.grid_state import get_dataset_version

    backend_request = auction_backend_edit_request(
        base_version=base_version,
        edits=edits,
        workspace_id=workspace_id,
        user_id=user_id,
        session_id=session_id,
        operation_type=operation_type,
        payload=payload,
    )
    service = AuctionGridEditService(workspace_id=workspace_id)
    try:
        await prepare_session_for_package_transaction(session)
        result = await run_package_grid_mutation(service.commit_edits(session, backend_request))
    except ApiException as error:
        if error.code == "stale-revision":
            current_version = await get_dataset_version(session, workspace_id, AUCTION_LOTS_TABLE_ID)
            raise AuctionGridEditConflictError(base_version=base_version, current_version=current_version) from error
        if error.status_code == 404:
            raise LookupError(error.message) from error
        raise ValueError(error.message) from error

    if result.rejected:
        reason = result.rejected[0].reason
        if reason == "row-not-found":
            raise LookupError(reason)
        raise ValueError(reason)

    updated_rows: list[AuctionLotsGridPullRow] = []
    for row in result.rows:
        await refresh_package_grid_row(session, row)
        updated_rows.append(
            AuctionLotsGridPullRow(
            id=auction_lot_grid_row_id(row.record),
            index=int(row.record.id),
            row=validate_datagrid_row_payload(row.record.datagrid_row),
        )
        )
    updated_row_ids = [row.id for row in updated_rows]
    history_status = getattr(result, "history_status", None)
    committed_cells = getattr(result, "committed", [])
    committed_payload = [
        {"rowId": item.row_id, "columnId": item.column_id, "revision": item.revision}
        for item in committed_cells
    ]
    if not committed_payload:
        committed_payload = [{"rowId": row_id, "revision": str(result.revision)} for row_id in updated_row_ids]
    return AuctionLotsGridEditResponse(
        operation_id=getattr(result, "operation_id", None),
        dataset_version=int(result.revision),
        updated_rows=updated_rows,
        revision=str(result.revision),
        committed=committed_payload,
        rejected=[],
        invalidation={"type": "rows", "rowIds": updated_row_ids, "reason": "edit"},
        rows=updated_rows,
        affected_rows=len(updated_row_ids),
        affected_cells=len(committed_payload),
        can_undo=getattr(history_status, "can_undo", None),
        can_redo=getattr(history_status, "can_redo", None),
        latest_undo_operation_id=getattr(history_status, "latest_undo_operation_id", None),
        latest_redo_operation_id=getattr(history_status, "latest_redo_operation_id", None),
    )


async def _find_record_by_row_id(session: AsyncSession, row_id: str) -> AuctionLotRecord | None:
    source, auction_id, lot_id = _parse_row_id(row_id)
    return await session.scalar(
        select(AuctionLotRecord)
        .where(
            AuctionLotRecord.source_code == source,
            AuctionLotRecord.auction_external_id == auction_id,
            AuctionLotRecord.lot_external_id == lot_id,
        )
        .with_for_update()
    )


def _parse_row_id(row_id: str) -> tuple[str, str, str]:
    parts = row_id.split(":", 2)
    if len(parts) != 3 or not all(part.strip() for part in parts):
        raise ValueError("rowId must use the stable source:auction:lot format")
    source, auction_id, lot_id = parts
    return source.strip(), auction_id.strip(), lot_id.strip()


def _prepare_edit(edit: AuctionLotsGridCellEdit) -> PreparedGridEdit:
    field_name = _workspace_field_for_column(edit.column_id)
    return PreparedGridEdit(
        row_id=edit.row_id,
        column_id=edit.column_id,
        field_name=field_name,
        value=_coerce_value(field_name, edit.value),
    )


def _workspace_field_for_column(column_id: str) -> str:
    field_name = WORKSPACE_EDIT_COLUMNS.get(column_id)
    if field_name is None:
        raise ValueError(f"Column is not editable: {column_id}")
    return field_name


def _coerce_value(field_name: str, value: Any) -> Any:
    if field_name in DECIMAL_EDIT_FIELDS:
        return _coerce_decimal(value, field_name)
    if field_name in BOOLEAN_EDIT_FIELDS:
        return _coerce_boolean(value, field_name)
    if field_name in DATETIME_EDIT_FIELDS:
        return _coerce_datetime(value, field_name)
    return _coerce_nullable_text(value, field_name)


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


def _coerce_boolean(value: Any, field_name: str) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"", "false", "0", "no", "off"}:
            return False
        if normalized in {"true", "1", "yes", "on"}:
            return True
    raise ValueError(f"{field_name} must be a boolean")


def _coerce_datetime(value: Any, field_name: str) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be an ISO datetime")
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ValueError(f"{field_name} must be an ISO datetime") from error


def _coerce_nullable_text(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict | list):
        raise ValueError(f"{field_name} must be text")
    normalized = str(value).strip()
    return normalized or None
