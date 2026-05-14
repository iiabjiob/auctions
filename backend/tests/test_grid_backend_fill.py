from __future__ import annotations

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID

from affino_grid_backend import ApiException

from app.services.grid_backend_fill import AuctionGridFillService, ProcurementGridFillService
from app.services.procurement_grid_fill import GridBackendFillRequest, GridBackendFillRange


class GridBackendFillTests(unittest.IsolatedAsyncioTestCase):
    def test_procurement_fill_service_uses_uuid_operation_ids(self) -> None:
        service = ProcurementGridFillService()

        operation_id = service.create_fill_operation_id()

        self.assertIsInstance(UUID(operation_id), UUID)

    async def test_procurement_fill_rejects_stale_revision_before_commit(self) -> None:
        service = ProcurementGridFillService()
        service._revision_service.get_revision = AsyncMock(return_value="6")
        request = GridBackendFillRequest(
            mode="copy",
            source_row_ids=["zakupki:source"],
            target_row_ids=["zakupki:target"],
            fill_columns=["quantity"],
            reference_columns=["quantity"],
            source_range=GridBackendFillRange(startRow=0, endRow=1),
            target_range=GridBackendFillRange(startRow=1, endRow=2),
            projection={},
            base_version=5,
        )

        with self.assertRaises(ApiException) as context:
            await service.commit_fill(SimpleNamespace(), request)

        self.assertEqual(context.exception.code, "stale-revision")

    async def test_create_fill_operation_delegates_to_edit_operation_writer(self) -> None:
        service = ProcurementGridFillService()
        service._edit_service.create_operation = AsyncMock()
        request = GridBackendFillRequest(
            mode="copy",
            source_row_ids=["zakupki:source"],
            target_row_ids=["zakupki:target"],
            fill_columns=["quantity"],
            reference_columns=["quantity"],
            source_range=GridBackendFillRange(startRow=0, endRow=1),
            target_range=GridBackendFillRange(startRow=1, endRow=2),
            projection={},
            metadata={"edits": [{"rowId": "zakupki:target", "columnId": "quantity"}]},
            base_version=5,
            user_id="u1",
            session_id="s1",
        )

        await service.create_fill_operation(SimpleNamespace(), "2d5b96fa-4f0d-4ff6-8b4f-fc7b6c77b8ea", {}, datetime.now(UTC), request)

        service._edit_service.create_operation.assert_awaited_once()
        delegated_request = service._edit_service.create_operation.await_args.args[3]
        self.assertEqual(delegated_request.operation_type, "fill")
        self.assertEqual(delegated_request.base_version, 5)
        self.assertEqual(delegated_request.user_id, "u1")

    async def test_create_cell_events_delegates_to_edit_cell_event_writer(self) -> None:
        service = ProcurementGridFillService()
        service._edit_service.create_cell_events = AsyncMock()

        await service.create_cell_events(SimpleNamespace(), "2d5b96fa-4f0d-4ff6-8b4f-fc7b6c77b8ea", [], datetime.now(UTC))

        service._edit_service.create_cell_events.assert_awaited_once()

    async def test_collect_history_status_delegates_as_fill_edit_request(self) -> None:
        service = ProcurementGridFillService()
        service._edit_service.collect_history_status = AsyncMock(return_value=None)
        request = GridBackendFillRequest(
            mode="copy",
            source_row_ids=["zakupki:source"],
            target_row_ids=["zakupki:target"],
            fill_columns=["quantity"],
            reference_columns=["quantity"],
            source_range=GridBackendFillRange(startRow=0, endRow=1),
            target_range=GridBackendFillRange(startRow=1, endRow=2),
            projection={},
            metadata={"edits": [{"rowId": "zakupki:target", "columnId": "quantity"}]},
            base_version=5,
            user_id="u1",
            session_id="s1",
        )

        await service.collect_history_status(
            SimpleNamespace(),
            request,
            operation_id="2d5b96fa-4f0d-4ff6-8b4f-fc7b6c77b8ea",
            affected_row_ids=["zakupki:target"],
            affected_indexes=[1],
            affected_cell_count=1,
            warnings=[],
            revision="6",
            rows=[],
        )

        service._edit_service.collect_history_status.assert_awaited_once()
        delegated_request = service._edit_service.collect_history_status.await_args.args[1]
        delegated_kwargs = service._edit_service.collect_history_status.await_args.kwargs
        self.assertEqual(delegated_request.operation_type, "fill")
        self.assertEqual(delegated_request.edits[0].row_id, "zakupki:target")
        self.assertEqual(delegated_request.edits[0].column_id, "quantity")
        self.assertEqual(delegated_kwargs["revision"], "6")

    def test_fill_value_uses_procurement_edit_normalization(self) -> None:
        service = ProcurementGridFillService()

        self.assertEqual(str(service.normalize_fill_value("quantity", "10,5")), "10.5")

    async def test_auction_collect_history_status_delegates_as_fill_edit_request(self) -> None:
        service = AuctionGridFillService()
        service._edit_service.collect_history_status = AsyncMock(return_value=None)
        request = GridBackendFillRequest(
            mode="copy",
            source_row_ids=["tbankrot:auction-1:lot-1"],
            target_row_ids=["tbankrot:auction-1:lot-2"],
            fill_columns=["marketValue"],
            reference_columns=["marketValue"],
            source_range=GridBackendFillRange(startRow=0, endRow=1),
            target_range=GridBackendFillRange(startRow=1, endRow=2),
            projection={},
            metadata={"edits": [{"rowId": "tbankrot:auction-1:lot-2", "columnId": "marketValue"}]},
            base_version=5,
            user_id="u1",
            session_id="s1",
        )

        await service.collect_history_status(
            SimpleNamespace(),
            request,
            operation_id="2d5b96fa-4f0d-4ff6-8b4f-fc7b6c77b8ea",
            affected_row_ids=["tbankrot:auction-1:lot-2"],
            affected_indexes=[1],
            affected_cell_count=1,
            warnings=[],
            revision="6",
            rows=[],
        )

        service._edit_service.collect_history_status.assert_awaited_once()
        delegated_request = service._edit_service.collect_history_status.await_args.args[1]
        self.assertEqual(delegated_request.operation_type, "fill")
        self.assertEqual(delegated_request.edits[0].row_id, "tbankrot:auction-1:lot-2")
        self.assertEqual(delegated_request.edits[0].column_id, "marketValue")


if __name__ == "__main__":
    unittest.main()
