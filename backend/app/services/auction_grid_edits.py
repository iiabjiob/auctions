from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auction import AuctionLotDetailCache, AuctionLotRecord
from app.models.grid import GridChangeEventModel
from app.schemas.auction_grid import (
    AuctionLotsGridCellEdit,
    AuctionLotsGridEditRequest,
    AuctionLotsGridEditResponse,
    AuctionLotsGridPullRow,
)
from app.services.auction_analysis_config import auction_analysis_config_service
from app.services.auction_datagrid_payload import validate_datagrid_row_payload
from app.services.auction_grid_state import AUCTION_LOTS_TABLE_ID, DEFAULT_GRID_WORKSPACE_ID, auction_lot_grid_row_id
from app.services.auction_scoring import (
    recalculate_record_rating,
    sync_record_from_detail_cache,
)
from app.services.auction_workspace import ensure_work_item
from app.services.lot_decision_report import generate_and_persist_lot_decision_report_snapshot
from app.services.grid_state import (
    bump_dataset_version,
    clear_redo_grid_operations,
    get_or_create_grid_revision,
    record_grid_operation,
)


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
    return await _commit_auction_lot_grid_operations(
        session,
        base_version=request.base_version,
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
    prepared_edits = [_prepare_edit(edit) for edit in edits]
    edits_by_row: dict[str, list[PreparedGridEdit]] = defaultdict(list)
    row_order: list[str] = []
    for edit in prepared_edits:
        if edit.row_id not in edits_by_row:
            row_order.append(edit.row_id)
        edits_by_row[edit.row_id].append(edit)

    revision = await get_or_create_grid_revision(session, workspace_id, AUCTION_LOTS_TABLE_ID)
    current_version = int(revision.dataset_version)
    if current_version != base_version:
        raise AuctionGridEditConflictError(base_version=base_version, current_version=current_version)

    runtime_config = await auction_analysis_config_service.get_runtime_config(session)
    updated_records: dict[str, AuctionLotRecord] = {}
    changed_fields_by_row: dict[str, set[str]] = {}
    undo_values: dict[tuple[str, str], dict[str, Any]] = {}
    redo_values: dict[tuple[str, str], dict[str, Any]] = {}

    for requested_row_id in row_order:
        record = await _find_record_by_row_id(session, requested_row_id)
        if record is None:
            raise LookupError(f"Lot row was not found for rowId={requested_row_id}")

        detail_cache = await session.scalar(
            select(AuctionLotDetailCache).where(AuctionLotDetailCache.lot_record_id == record.id)
        )
        if detail_cache is not None:
            sync_record_from_detail_cache(record, detail_cache)
        work_item = await ensure_work_item(session, record)
        stable_row_id = auction_lot_grid_row_id(record)
        changed_fields_by_row.setdefault(stable_row_id, set())

        for edit in edits_by_row[requested_row_id]:
            key = (stable_row_id, edit.field_name)
            if key not in undo_values:
                undo_values[key] = {
                    "rowId": stable_row_id,
                    "columnId": edit.column_id,
                    "field": edit.field_name,
                    "value": _json_value(getattr(work_item, edit.field_name)),
                }
            setattr(work_item, edit.field_name, edit.value)
            redo_values[key] = {
                "rowId": stable_row_id,
                "columnId": edit.column_id,
                "field": edit.field_name,
                "value": _json_value(edit.value),
            }
            changed_fields_by_row[stable_row_id].add(edit.field_name)

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
        await generate_and_persist_lot_decision_report_snapshot(session, record, detail_cache, work_item)
        updated_records[stable_row_id] = record

    resulting_version = await bump_dataset_version(session, workspace_id, AUCTION_LOTS_TABLE_ID)
    for row_id, changed_fields in changed_fields_by_row.items():
        session.add(
            GridChangeEventModel(
                workspace_id=workspace_id,
                table_id=AUCTION_LOTS_TABLE_ID,
                dataset_version=resulting_version,
                event_type="row_updated",
                row_id=row_id,
                payload={"source": "grid_edit", "changed_fields": sorted(changed_fields)},
            )
        )

    await clear_redo_grid_operations(
        session,
        workspace_id=workspace_id,
        table_id=AUCTION_LOTS_TABLE_ID,
        user_id=user_id,
        session_id=session_id,
    )
    await record_grid_operation(
        session,
        workspace_id=workspace_id,
        table_id=AUCTION_LOTS_TABLE_ID,
        operation_type=operation_type,
        user_id=user_id,
        session_id=session_id,
        base_version=base_version,
        resulting_version=resulting_version,
        payload=payload,
        undo_payload={"edits": list(undo_values.values())},
        redo_payload={"edits": list(redo_values.values())},
    )
    await session.flush()

    return AuctionLotsGridEditResponse(
        dataset_version=resulting_version,
        updated_rows=[
            AuctionLotsGridPullRow(
                id=row_id,
                index=int(record.id),
                row=validate_datagrid_row_payload(record.datagrid_row),
            )
            for row_id, record in updated_records.items()
        ],
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


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value
