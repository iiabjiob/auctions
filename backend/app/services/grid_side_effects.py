from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auction import AuctionLotDetailCache, AuctionLotRecord, AuctionLotWorkItem
from app.models.grid import GridSideEffectTaskModel
from app.models.procurement import ProcurementLotRecord
from app.services.auction_grid_state import AUCTION_LOTS_TABLE_ID
from app.services.lot_decision_report import generate_and_persist_lot_decision_report_snapshot
from app.services.procurement_grid_state import PROCUREMENT_LOTS_TABLE_ID
from app.services.procurement_notifications import enqueue_procurement_telegram_notifications


logger = logging.getLogger(__name__)

GRID_SIDE_EFFECT_STATUS_PENDING = "pending"
GRID_SIDE_EFFECT_STATUS_PROCESSING = "processing"
GRID_SIDE_EFFECT_STATUS_DONE = "done"
GRID_SIDE_EFFECT_STATUS_FAILED = "failed"
GRID_SIDE_EFFECT_AUCTION_DECISION_REPORT = "auction_decision_report"
GRID_SIDE_EFFECT_PROCUREMENT_NOTIFICATIONS = "procurement_notifications"
GRID_SIDE_EFFECT_WORKER_ID = "grid-side-effects-worker"


@dataclass(frozen=True)
class GridSideEffectBatchResult:
    selected: int = 0
    processed: int = 0
    failed: int = 0
    retried: int = 0


async def enqueue_grid_side_effect_tasks(
    session: AsyncSession,
    *,
    operation_id: str | UUID | None,
    workspace_id: str,
    table_id: str,
    row_ids: list[str],
    trigger_type: str = "commit",
    max_attempts: int = 3,
) -> int:
    if operation_id is None or not row_ids:
        return 0
    effect_type = _effect_type_for_table(table_id)
    operation_uuid = UUID(str(operation_id))
    unique_row_ids = list(dict.fromkeys(row_ids))
    values = [
        {
            "operation_id": operation_uuid,
            "workspace_id": workspace_id,
            "table_id": table_id,
            "row_id": row_id,
            "effect_type": effect_type,
            "trigger_type": trigger_type,
            "status": GRID_SIDE_EFFECT_STATUS_PENDING,
            "attempts": 0,
            "max_attempts": max(1, int(max_attempts)),
            "payload": {},
        }
        for row_id in unique_row_ids
    ]
    statement = insert(GridSideEffectTaskModel).values(values)
    statement = statement.on_conflict_do_nothing(
        constraint="uq_grid_side_effect_tasks_operation_row_effect_trigger",
    )
    try:
        async with session.begin_nested():
            result = await session.execute(statement)
    except SQLAlchemyError:
        logger.exception(
            "Failed to enqueue grid side effect tasks",
            extra={"table_id": table_id, "operation_id": str(operation_uuid), "row_count": len(unique_row_ids)},
        )
        return 0
    return int(result.rowcount or 0)


async def run_grid_side_effect_batch(
    session: AsyncSession,
    *,
    limit: int,
    worker_id: str = GRID_SIDE_EFFECT_WORKER_ID,
    claim_ttl_seconds: int = 120,
    max_attempts: int = 3,
    base_backoff_seconds: int = 60,
) -> GridSideEffectBatchResult:
    tasks = await claim_grid_side_effect_tasks(
        session,
        limit=limit,
        worker_id=worker_id,
        claim_ttl_seconds=claim_ttl_seconds,
        max_attempts=max_attempts,
    )
    await session.commit()
    result = GridSideEffectBatchResult(selected=len(tasks))
    processed = 0
    failed = 0
    retried = 0
    for task in tasks:
        try:
            await process_grid_side_effect_task(session, task)
            task.status = GRID_SIDE_EFFECT_STATUS_DONE
            task.processed_at = datetime.now(UTC)
            task.claimed_by = None
            task.claimed_at = None
            task.claim_expires_at = None
            task.last_error = None
            processed += 1
        except Exception as error:
            await session.rollback()
            task = await session.get(GridSideEffectTaskModel, task.id)
            if task is None:
                continue
            logger.exception("Grid side effect task failed", extra={"task_id": task.id, "effect_type": task.effect_type})
            failed += 1
            task.last_error = str(error)[:2000]
            task.claimed_by = None
            task.claimed_at = None
            task.claim_expires_at = None
            if task.attempts >= task.max_attempts:
                task.status = GRID_SIDE_EFFECT_STATUS_FAILED
            else:
                task.status = GRID_SIDE_EFFECT_STATUS_PENDING
                task.next_attempt_at = datetime.now(UTC) + timedelta(
                    seconds=max(1, int(base_backoff_seconds)) * (2 ** max(0, task.attempts - 1))
                )
                retried += 1
        await session.commit()
    return GridSideEffectBatchResult(selected=len(tasks), processed=processed, failed=failed, retried=retried)


async def claim_grid_side_effect_tasks(
    session: AsyncSession,
    *,
    limit: int,
    worker_id: str,
    claim_ttl_seconds: int,
    max_attempts: int,
) -> list[GridSideEffectTaskModel]:
    now = datetime.now(UTC)
    claim_expires_at = now + timedelta(seconds=max(1, int(claim_ttl_seconds)))
    statement = (
        select(GridSideEffectTaskModel)
        .where(GridSideEffectTaskModel.next_attempt_at <= now)
        .where(GridSideEffectTaskModel.attempts < GridSideEffectTaskModel.max_attempts)
        .where(
            or_(
                GridSideEffectTaskModel.status == GRID_SIDE_EFFECT_STATUS_PENDING,
                (
                    (GridSideEffectTaskModel.status == GRID_SIDE_EFFECT_STATUS_PROCESSING)
                    & (GridSideEffectTaskModel.claim_expires_at < now)
                ),
            )
        )
        .order_by(GridSideEffectTaskModel.created_at.asc(), GridSideEffectTaskModel.id.asc())
        .limit(max(1, int(limit)))
        .with_for_update(skip_locked=True)
    )
    tasks = list((await session.scalars(statement)).all())
    for task in tasks:
        task.status = GRID_SIDE_EFFECT_STATUS_PROCESSING
        task.claimed_by = worker_id
        task.claimed_at = now
        task.claim_expires_at = claim_expires_at
        task.max_attempts = max(1, int(max_attempts))
        task.attempts += 1
    await session.flush()
    return tasks


async def process_grid_side_effect_task(session: AsyncSession, task: GridSideEffectTaskModel) -> None:
    if task.effect_type == GRID_SIDE_EFFECT_AUCTION_DECISION_REPORT:
        await _process_auction_decision_report_task(session, task.row_id)
        return
    if task.effect_type == GRID_SIDE_EFFECT_PROCUREMENT_NOTIFICATIONS:
        await _process_procurement_notifications_task(session, task.row_id)
        return
    raise ValueError(f"Unsupported grid side effect type: {task.effect_type}")


async def reset_stale_grid_side_effect_tasks(session: AsyncSession) -> int:
    now = datetime.now(UTC)
    result = await session.execute(
        update(GridSideEffectTaskModel)
        .where(GridSideEffectTaskModel.status == GRID_SIDE_EFFECT_STATUS_PROCESSING)
        .where(GridSideEffectTaskModel.claim_expires_at < now)
        .values(
            status=GRID_SIDE_EFFECT_STATUS_PENDING,
            claimed_by=None,
            claimed_at=None,
            claim_expires_at=None,
            next_attempt_at=now,
        )
    )
    return int(result.rowcount or 0)


async def _process_auction_decision_report_task(session: AsyncSession, row_id: str) -> None:
    source_code, auction_external_id, lot_external_id = _parse_auction_row_id(row_id)
    record = await session.scalar(
        select(AuctionLotRecord).where(
            AuctionLotRecord.source_code == source_code,
            AuctionLotRecord.auction_external_id == auction_external_id,
            AuctionLotRecord.lot_external_id == lot_external_id,
        )
    )
    if record is None:
        return
    detail_cache = await session.scalar(select(AuctionLotDetailCache).where(AuctionLotDetailCache.lot_record_id == record.id))
    work_item = await session.scalar(select(AuctionLotWorkItem).where(AuctionLotWorkItem.lot_record_id == record.id))
    await generate_and_persist_lot_decision_report_snapshot(session, record, detail_cache, work_item)


async def _process_procurement_notifications_task(session: AsyncSession, row_id: str) -> None:
    source_code, external_id = _parse_procurement_row_id(row_id)
    record = await session.scalar(
        select(ProcurementLotRecord).where(
            ProcurementLotRecord.source_code == source_code,
            ProcurementLotRecord.external_id == external_id,
        )
    )
    if record is None:
        return
    await enqueue_procurement_telegram_notifications(session, record)


def _effect_type_for_table(table_id: str) -> str:
    if table_id == AUCTION_LOTS_TABLE_ID:
        return GRID_SIDE_EFFECT_AUCTION_DECISION_REPORT
    if table_id == PROCUREMENT_LOTS_TABLE_ID:
        return GRID_SIDE_EFFECT_PROCUREMENT_NOTIFICATIONS
    raise ValueError(f"Unsupported grid side effect tableId: {table_id}")


def _parse_auction_row_id(row_id: str) -> tuple[str, str, str]:
    parts = row_id.split(":", 2)
    if len(parts) != 3 or not all(part.strip() for part in parts):
        raise ValueError("Auction rowId must use source:auction:lot format")
    return parts[0].strip(), parts[1].strip(), parts[2].strip()


def _parse_procurement_row_id(row_id: str) -> tuple[str, str]:
    parts = row_id.split(":", 1)
    if len(parts) != 2 or not all(part.strip() for part in parts):
        raise ValueError("Procurement rowId must use source:external format")
    return parts[0].strip(), parts[1].strip()
