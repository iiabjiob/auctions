from __future__ import annotations

import unittest
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID

from affino_grid_backend import ApiException

from app.models.auction import AuctionLotRecord, AuctionLotWorkItem
from app.models.grid import GridCellEventModel, GridOperationModel
from app.models.procurement import ProcurementLotRecord
from app.services.grid_backend_edits import (
    AuctionGridEditRow,
    AuctionGridEditService,
    GridBackendCellEdit,
    GridBackendEditRequest,
    ProcurementGridEditService,
    auction_backend_edit_request,
    procurement_backend_edit_request,
)
from app.services.auction_grid_state import AUCTION_LOTS_TABLE_ID
from app.services.procurement_grid_state import DEFAULT_GRID_WORKSPACE_ID, PROCUREMENT_LOTS_TABLE_ID


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


def make_auction_record() -> AuctionLotRecord:
    return AuctionLotRecord(
        id=2,
        source_code="tbankrot",
        auction_external_id="auction-1",
        lot_external_id="lot-1",
        lot_name="Лот",
        content_hash="hash",
        datagrid_row={"row_id": "tbankrot:auction-1:lot-1"},
        normalized_item={},
        updated_at=datetime.now(UTC),
    )


class FakeScalarResult:
    def __init__(self, value: object | None) -> None:
        self.value = value

    def all(self) -> list[object]:
        return [] if self.value is None else [self.value]


class FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.flush_count = 0
        self.scalar_results: list[object | None] = []

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        self.flush_count += 1

    async def scalar(self, statement: object) -> object | None:
        del statement
        if self.scalar_results:
            return self.scalar_results.pop(0)
        return None


class GridBackendEditsTests(unittest.IsolatedAsyncioTestCase):
    def test_procurement_request_adapter_preserves_public_request_shape(self) -> None:
        edit = SimpleNamespace(row_id="zakupki:123", column_id="quantity", value="10")

        request = procurement_backend_edit_request(
            base_version=5,
            edits=[edit],
            workspace_id=DEFAULT_GRID_WORKSPACE_ID,
            user_id="u1",
            session_id="s1",
            payload={"edits": [{"rowId": "zakupki:123"}]},
        )

        self.assertEqual(request.base_revision, "5")
        self.assertEqual(request.base_version, 5)
        self.assertEqual(request.user_id, "u1")
        self.assertEqual(request.edits[0].row_id, "zakupki:123")

    def test_procurement_service_uses_uuid_operation_ids(self) -> None:
        service = ProcurementGridEditService()

        operation_id = service.create_edit_operation_id()

        self.assertIsInstance(UUID(operation_id), UUID)

    def test_procurement_service_normalizes_and_sets_record_values(self) -> None:
        service = ProcurementGridEditService()
        record = make_procurement_record()

        quantity = service.normalize_edit_value("quantity", "10,5")
        service.set_row_value(record, "quantity", quantity)
        service.set_row_value(record, "workflowStatus", service.normalize_edit_value("workflowStatus", "На решение"))

        self.assertEqual(record.quantity, Decimal("10.5"))
        self.assertEqual(record.workflow_status, "decision")
        self.assertIn("decision", record.search_text or "")

    async def test_create_operation_records_scope_and_clears_redo(self) -> None:
        service = ProcurementGridEditService(workspace_id=DEFAULT_GRID_WORKSPACE_ID)
        session = FakeSession()
        operation_id = service.create_edit_operation_id()
        request = GridBackendEditRequest(
            base_revision="5",
            base_version=5,
            edits=[GridBackendCellEdit(row_id="zakupki:123", column_id="comment", value="next")],
            workspace_id=DEFAULT_GRID_WORKSPACE_ID,
            user_id="u1",
            session_id="s1",
            payload={"edits": []},
        )

        with patch("app.services.grid_backend_edits.clear_redo_grid_operations", AsyncMock(return_value=1)) as clear_redo:
            await service.create_operation(session, operation_id, datetime.now(UTC), request)

        clear_redo.assert_awaited_once_with(
            session,
            workspace_id=DEFAULT_GRID_WORKSPACE_ID,
            table_id=PROCUREMENT_LOTS_TABLE_ID,
            user_id="u1",
            session_id="s1",
        )
        operations = [item for item in session.added if isinstance(item, GridOperationModel)]
        self.assertEqual(len(operations), 1)
        self.assertEqual(operations[0].id, UUID(operation_id))
        self.assertEqual(operations[0].operation_type, "edit")
        self.assertEqual(operations[0].base_version, 5)

    async def test_create_cell_events_persists_events_and_payloads(self) -> None:
        service = ProcurementGridEditService(workspace_id=DEFAULT_GRID_WORKSPACE_ID)
        operation_id = service.create_edit_operation_id()
        operation = GridOperationModel(
            id=UUID(operation_id),
            workspace_id=DEFAULT_GRID_WORKSPACE_ID,
            table_id=PROCUREMENT_LOTS_TABLE_ID,
            operation_type="edit",
        )
        session = FakeSession()
        session.scalar_results.append(operation)
        event = SimpleNamespace(row_id="zakupki:123", column_id="quantity", before_value=Decimal("1"), after_value=Decimal("2"))

        await service.create_cell_events(session, operation_id, [event], datetime.now(UTC))

        cell_events = [item for item in session.added if isinstance(item, GridCellEventModel)]
        self.assertEqual(len(cell_events), 1)
        self.assertEqual(cell_events[0].before_value, {"value": "1"})
        self.assertEqual(cell_events[0].after_value, {"value": "2"})
        self.assertEqual(operation.undo_payload["edits"][0]["field"], "quantity")
        self.assertEqual(operation.redo_payload["edits"][0]["value"], "2")

    async def test_invalid_operation_id_is_rejected(self) -> None:
        service = ProcurementGridEditService()

        with self.assertRaises(ApiException):
            await service.ensure_operation_id_available(FakeSession(), "edit-not-a-uuid")

    def test_auction_request_adapter_preserves_public_request_shape(self) -> None:
        edit = SimpleNamespace(row_id="tbankrot:auction-1:lot-1", column_id="marketValue", value="100")

        request = auction_backend_edit_request(
            base_version=7,
            edits=[edit],
            workspace_id=DEFAULT_GRID_WORKSPACE_ID,
            user_id="u1",
            session_id="s1",
            payload={"edits": [{"rowId": "tbankrot:auction-1:lot-1"}]},
        )

        self.assertEqual(request.base_revision, "7")
        self.assertEqual(request.base_version, 7)
        self.assertEqual(request.user_id, "u1")
        self.assertEqual(request.edits[0].column_id, "marketValue")

    def test_auction_service_normalizes_and_sets_work_item_values(self) -> None:
        service = AuctionGridEditService()
        record = make_auction_record()
        work_item = AuctionLotWorkItem(lot_record_id=record.id, analogs=[])
        row = AuctionGridEditRow(
            record=record,
            work_item=work_item,
            detail_cache=None,
            runtime_config=SimpleNamespace(
                category_keywords={},
                exclusion_keywords=(),
                legal_risk_rules=None,
                owner_profile=None,
                dimension_weights=None,
            ),
        )

        with (
            patch("app.services.grid_backend_edits.recalculate_record_rating") as recalculate,
            patch("app.services.grid_backend_edits.update_record_search_text") as update_search,
        ):
            service.set_row_value(row, "marketValue", service.normalize_edit_value("marketValue", "123.45"))
            service.set_row_value(row, "excludeFromAnalysis", service.normalize_edit_value("excludeFromAnalysis", True))

        self.assertEqual(work_item.market_value, Decimal("123.45"))
        self.assertTrue(work_item.exclude_from_analysis)
        self.assertEqual(recalculate.call_count, 2)
        self.assertEqual(update_search.call_count, 2)

    async def test_auction_create_operation_records_scope_and_clears_redo(self) -> None:
        service = AuctionGridEditService(workspace_id=DEFAULT_GRID_WORKSPACE_ID)
        session = FakeSession()
        operation_id = service.create_edit_operation_id()
        request = GridBackendEditRequest(
            base_revision="5",
            base_version=5,
            edits=[GridBackendCellEdit(row_id="tbankrot:auction-1:lot-1", column_id="comment", value="next")],
            workspace_id=DEFAULT_GRID_WORKSPACE_ID,
            user_id="u1",
            session_id="s1",
            payload={"edits": []},
        )

        with patch("app.services.grid_backend_edits.clear_redo_grid_operations", AsyncMock(return_value=1)) as clear_redo:
            await service.create_operation(session, operation_id, datetime.now(UTC), request)

        clear_redo.assert_awaited_once_with(
            session,
            workspace_id=DEFAULT_GRID_WORKSPACE_ID,
            table_id=AUCTION_LOTS_TABLE_ID,
            user_id="u1",
            session_id="s1",
        )
        operations = [item for item in session.added if isinstance(item, GridOperationModel)]
        self.assertEqual(len(operations), 1)
        self.assertEqual(operations[0].id, UUID(operation_id))
        self.assertEqual(operations[0].table_id, AUCTION_LOTS_TABLE_ID)

    async def test_auction_create_cell_events_persists_events_and_payloads(self) -> None:
        service = AuctionGridEditService(workspace_id=DEFAULT_GRID_WORKSPACE_ID)
        operation_id = service.create_edit_operation_id()
        operation = GridOperationModel(
            id=UUID(operation_id),
            workspace_id=DEFAULT_GRID_WORKSPACE_ID,
            table_id=AUCTION_LOTS_TABLE_ID,
            operation_type="edit",
        )
        session = FakeSession()
        session.scalar_results.append(operation)
        event = SimpleNamespace(
            row_id="tbankrot:auction-1:lot-1",
            column_id="marketValue",
            before_value=Decimal("1"),
            after_value=Decimal("2"),
        )

        await service.create_cell_events(session, operation_id, [event], datetime.now(UTC))

        cell_events = [item for item in session.added if isinstance(item, GridCellEventModel)]
        self.assertEqual(len(cell_events), 1)
        self.assertEqual(cell_events[0].table_id, AUCTION_LOTS_TABLE_ID)
        self.assertEqual(cell_events[0].before_value, {"value": "1"})
        self.assertEqual(operation.undo_payload["edits"][0]["field"], "market_value")
        self.assertEqual(operation.redo_payload["edits"][0]["value"], "2")


if __name__ == "__main__":
    unittest.main()
