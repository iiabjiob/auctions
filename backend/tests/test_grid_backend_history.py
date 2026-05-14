from __future__ import annotations

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.models.grid import GridCellEventModel, GridOperationModel
from app.models.procurement import ProcurementLotRecord
from app.services.grid_backend_history import (
    ProcurementGridHistoryService,
    get_grid_history_status,
    redo_grid_history,
    undo_grid_history,
)
from app.services.procurement_grid_state import DEFAULT_GRID_WORKSPACE_ID, PROCUREMENT_LOTS_TABLE_ID


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

    async def test_auction_history_is_delegated_to_existing_service(self) -> None:
        session = AsyncMock()
        with patch("app.services.grid_backend_history.undo_auction_lot_grid_history", new_callable=AsyncMock) as undo:
            undo.return_value = SimpleNamespace(dataset_version=10, updated_rows=[])

            response = await undo_grid_history(
                session,
                workspace_id=DEFAULT_GRID_WORKSPACE_ID,
                table_id="auction-lots",
                user_id="u1",
                session_id="s1",
            )

        self.assertEqual(response.dataset_version, 10)
        undo.assert_awaited_once()

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

