from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError

from app.models.grid import GridSideEffectTaskModel
from app.services.auction_grid_state import AUCTION_LOTS_TABLE_ID
from app.services.grid_side_effects import (
    GRID_SIDE_EFFECT_AUCTION_DECISION_REPORT,
    GRID_SIDE_EFFECT_PROCUREMENT_NOTIFICATIONS,
    enqueue_grid_side_effect_tasks,
    process_grid_side_effect_task,
)
from app.services.procurement_grid_state import DEFAULT_GRID_WORKSPACE_ID, PROCUREMENT_LOTS_TABLE_ID


class FakeSession:
    def __init__(self) -> None:
        self.execute = AsyncMock(return_value=SimpleNamespace(rowcount=0))
        self.scalar_results: list[object | None] = []

    async def scalar(self, statement: object) -> object | None:
        del statement
        if self.scalar_results:
            return self.scalar_results.pop(0)
        return None

    def begin_nested(self):
        return FakeNestedTransaction()


class FakeNestedTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class GridSideEffectsTests(unittest.IsolatedAsyncioTestCase):
    async def test_enqueue_deduplicates_row_ids_and_uses_operation_scope(self) -> None:
        session = FakeSession()
        session.execute.return_value = SimpleNamespace(rowcount=1)
        operation_id = uuid4()

        inserted = await enqueue_grid_side_effect_tasks(
            session,
            operation_id=operation_id,
            workspace_id=DEFAULT_GRID_WORKSPACE_ID,
            table_id=AUCTION_LOTS_TABLE_ID,
            row_ids=["tbankrot:auction-1:lot-1", "tbankrot:auction-1:lot-1"],
        )

        self.assertEqual(inserted, 1)
        session.execute.assert_awaited_once()

    async def test_enqueue_failure_does_not_fail_core_grid_mutation(self) -> None:
        session = FakeSession()
        session.execute.side_effect = SQLAlchemyError("outbox unavailable")

        inserted = await enqueue_grid_side_effect_tasks(
            session,
            operation_id=uuid4(),
            workspace_id=DEFAULT_GRID_WORKSPACE_ID,
            table_id=AUCTION_LOTS_TABLE_ID,
            row_ids=["tbankrot:auction-1:lot-1"],
        )

        self.assertEqual(inserted, 0)

    async def test_process_auction_task_generates_decision_report_snapshot(self) -> None:
        session = FakeSession()
        record = SimpleNamespace(id=10)
        detail_cache = SimpleNamespace(lot_record_id=10)
        work_item = SimpleNamespace(lot_record_id=10)
        session.scalar_results.extend([record, detail_cache, work_item])
        task = GridSideEffectTaskModel(
            operation_id=uuid4(),
            workspace_id=DEFAULT_GRID_WORKSPACE_ID,
            table_id=AUCTION_LOTS_TABLE_ID,
            row_id="tbankrot:auction-1:lot-1",
            effect_type=GRID_SIDE_EFFECT_AUCTION_DECISION_REPORT,
            trigger_type="commit",
        )

        with patch("app.services.grid_side_effects.generate_and_persist_lot_decision_report_snapshot", new_callable=AsyncMock) as generate:
            await process_grid_side_effect_task(session, task)

        generate.assert_awaited_once_with(session, record, detail_cache, work_item)

    async def test_process_procurement_task_enqueues_notifications(self) -> None:
        session = FakeSession()
        record = SimpleNamespace(id=20)
        session.scalar_results.append(record)
        task = GridSideEffectTaskModel(
            operation_id=uuid4(),
            workspace_id=DEFAULT_GRID_WORKSPACE_ID,
            table_id=PROCUREMENT_LOTS_TABLE_ID,
            row_id="zakupki:123",
            effect_type=GRID_SIDE_EFFECT_PROCUREMENT_NOTIFICATIONS,
            trigger_type="commit",
        )

        with patch("app.services.grid_side_effects.enqueue_procurement_telegram_notifications", new_callable=AsyncMock) as enqueue:
            await process_grid_side_effect_task(session, task)

        enqueue.assert_awaited_once_with(session, record)


if __name__ == "__main__":
    unittest.main()
