from __future__ import annotations

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.models.grid import GridCellEventModel, GridChangeEventModel, GridOperationModel
from app.models.procurement import ProcurementLotRecord
from app.services.grid_backend_history import (
    ProcurementGridHistoryService,
    get_grid_history_status,
    redo_grid_history,
    undo_grid_history,
)
from app.services.procurement_grid_state import DEFAULT_GRID_WORKSPACE_ID, PROCUREMENT_LOTS_TABLE_ID


class FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.flush_count = 0
        self.refreshed: list[object] = []

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        self.flush_count += 1

    async def refresh(self, value: object) -> None:
        self.refreshed.append(value)


def make_procurement_record() -> ProcurementLotRecord:
    return ProcurementLotRecord(
        id=1,
        source_code="zakupki",
        external_id="123",
        registry_number="0123456789",
        title="Поставка спецодежды",
        content_hash="hash",
        workflow_status="new",
        matched_keywords=[],
        excluded_keywords=[],
        attractiveness_score=0,
        attractiveness_level="low",
        attractiveness_reasons=[],
        calculator_inputs={},
        calculator_scenarios={},
        normalized_item={},
        raw_item={},
        updated_at=datetime.now(UTC),
    )


class GridBackendHistoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_procurement_status_uses_package_history_scope(self) -> None:
        session = AsyncMock()
        with patch("app.services.grid_backend_history._find_history_operation", new_callable=AsyncMock) as finder:
            finder.side_effect = [SimpleNamespace(id="undo"), None]

            status = await get_grid_history_status(
                session,
                workspace_id=DEFAULT_GRID_WORKSPACE_ID,
                table_id=PROCUREMENT_LOTS_TABLE_ID,
                user_id="u1",
                session_id="s1",
            )

        self.assertTrue(status.can_undo)
        self.assertFalse(status.can_redo)
        self.assertEqual(finder.await_count, 2)

    async def test_auction_history_uses_package_history_scope(self) -> None:
        session = AsyncMock()
        operation = SimpleNamespace(id="operation")
        next_undo_operation = SimpleNamespace(id="previous-operation")
        with patch("app.services.grid_backend_history._find_history_operation", new_callable=AsyncMock) as finder:
            with patch("app.services.grid_backend_history.AuctionGridHistoryService") as service_type:
                with patch("app.services.grid_backend_history._operation_changed_fields", new_callable=AsyncMock) as fields:
                    service = service_type.return_value
                    service.apply_loaded_operation = AsyncMock(
                        return_value=SimpleNamespace(revision="10", rows=[], committed_row_ids=[])
                    )
                    finder.side_effect = [operation, next_undo_operation, operation]
                    fields.return_value = {}

                    response = await undo_grid_history(
                        session,
                        workspace_id=DEFAULT_GRID_WORKSPACE_ID,
                        table_id="auction-lots",
                        user_id="u1",
                        session_id="s1",
                    )

        self.assertEqual(response.dataset_version, 10)
        self.assertTrue(response.can_undo)
        self.assertTrue(response.can_redo)
        self.assertEqual(response.latest_undo_operation_id, "previous-operation")
        self.assertEqual(response.latest_redo_operation_id, "operation")
        self.assertEqual(finder.await_count, 3)
        service.apply_loaded_operation.assert_awaited_once_with(session, operation, "undo")

    async def test_procurement_history_writes_change_event(self) -> None:
        session = FakeSession()
        operation = SimpleNamespace(id=uuid4())
        record = make_procurement_record()
        with (
            patch("app.services.grid_backend_history._find_history_operation", new_callable=AsyncMock) as finder,
            patch("app.services.grid_backend_history.ProcurementGridHistoryService") as service_type,
            patch("app.services.grid_backend_history._operation_changed_fields", new_callable=AsyncMock) as fields,
            patch("app.services.grid_backend_history._persist_history_side_effects", new_callable=AsyncMock) as side_effects,
            patch("app.services.grid_backend_history.enqueue_grid_side_effect_tasks", new_callable=AsyncMock) as enqueue_side_effects,
        ):
            service = service_type.return_value
            service.apply_loaded_operation = AsyncMock(return_value=SimpleNamespace(revision="9", rows=[record]))
            finder.side_effect = [operation, None, operation]
            fields.return_value = {"zakupki:123": {"quantity"}}

            response = await undo_grid_history(
                session,
                workspace_id=DEFAULT_GRID_WORKSPACE_ID,
                table_id=PROCUREMENT_LOTS_TABLE_ID,
                user_id="u1",
                session_id="s1",
            )

        self.assertEqual(response.dataset_version, 9)
        self.assertEqual(session.flush_count, 1)
        self.assertEqual(session.refreshed, [record])
        self.assertEqual(response.updated_rows[0].id, "zakupki:123")
        side_effects.assert_awaited_once()
        enqueue_side_effects.assert_awaited_once()
        changes = [item for item in session.added if isinstance(item, GridChangeEventModel)]
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].table_id, PROCUREMENT_LOTS_TABLE_ID)
        self.assertEqual(changes[0].dataset_version, 9)
        self.assertEqual(changes[0].row_id, "zakupki:123")
        self.assertEqual(
            changes[0].payload,
            {
                "source": "grid_history_undo",
                "operation_id": str(operation.id),
                "changed_fields": ["quantity"],
            },
        )

    async def test_unsupported_table_rejected(self) -> None:
        with self.assertRaises(ValueError):
            await redo_grid_history(
                AsyncMock(),
                workspace_id=DEFAULT_GRID_WORKSPACE_ID,
                table_id="unknown",
                user_id=None,
                session_id=None,
            )

    def test_procurement_service_maps_cell_event_values_and_status(self) -> None:
        service = ProcurementGridHistoryService(workspace_id=DEFAULT_GRID_WORKSPACE_ID)
        operation = GridOperationModel(
            workspace_id=DEFAULT_GRID_WORKSPACE_ID,
            table_id=PROCUREMENT_LOTS_TABLE_ID,
            operation_type="edit",
        )
        event = GridCellEventModel(
            operation_id=operation.id,
            workspace_id=DEFAULT_GRID_WORKSPACE_ID,
            table_id=PROCUREMENT_LOTS_TABLE_ID,
            row_id="zakupki:1",
            column_id="comment",
            before_value={"value": "old"},
            after_value={"value": "new"},
        )

        self.assertEqual(service.get_operation_status(operation), "applied")
        service.set_operation_status(operation, "undone")
        self.assertEqual(service.get_operation_status(operation), "undone")
        self.assertEqual(service.event_before_value(event), "old")
        self.assertEqual(service.event_after_value(event), "new")
        self.assertEqual(service.normalize_edit_value("comment", " text "), "text")

    def test_procurement_service_updates_record_side_effects(self) -> None:
        service = ProcurementGridHistoryService(workspace_id=DEFAULT_GRID_WORKSPACE_ID)
        record = ProcurementLotRecord(
            source_code="zakupki",
            external_id="1",
            registry_number="1",
            content_hash="h",
            workflow_status="new",
            attractiveness_score=0,
            attractiveness_level="low",
            attractiveness_reasons=[],
            matched_keywords=[],
            excluded_keywords=[],
            calculator_inputs={},
            calculator_scenarios={},
            normalized_item={},
            raw_item={},
            updated_at=datetime.now(UTC),
        )

        service.set_row_value(record, "comment", "next")

        self.assertEqual(record.comment, "next")
        self.assertEqual(service.get_row_id(record), "zakupki:1")
