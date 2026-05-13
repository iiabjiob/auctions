from __future__ import annotations

import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, patch

from fastapi import HTTPException

from app.api.procurement_lots_grid_router import commit_procurement_lots_edits
from app.models.grid import GridChangeEventModel
from app.models.procurement import ProcurementLotRecord
from app.schemas.procurement_grid import ProcurementLotsGridEditRequest
from app.services.procurement_grid_edits import (
    ProcurementGridEditConflictError,
    _procurement_field_for_column,
    commit_procurement_lot_grid_edits,
)


def make_record() -> ProcurementLotRecord:
    return ProcurementLotRecord(
        id=1,
        source_code="zakupki",
        external_id="123",
        registry_number="0123456789",
        law="44-FZ",
        title="Поставка спецодежды",
        status="Подача заявок",
        customer_name="Заказчик",
        customer_inn="7700000000",
        initial_price="100 000 ₽",
        initial_price_value=Decimal("100000"),
        content_hash="hash",
        workflow_status="new",
        matched_keywords=[],
        excluded_keywords=[],
        attractiveness_score=55,
        attractiveness_level="medium",
        attractiveness_reasons=[],
        normalized_item={},
        raw_item={},
    )


class FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.flush_count = 0
        self.commit_count = 0
        self.rollback_count = 0

    async def scalar(self, statement: object) -> None:
        return None

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        self.flush_count += 1

    async def commit(self) -> None:
        self.commit_count += 1

    async def rollback(self) -> None:
        self.rollback_count += 1


class ProcurementGridEditsTests(unittest.IsolatedAsyncioTestCase):
    async def test_commit_edits_updates_record_revision_events_operation_and_search_text(self) -> None:
        record = make_record()
        session = FakeSession()
        request = ProcurementLotsGridEditRequest.model_validate(
            {
                "baseVersion": 5,
                "edits": [
                    {"rowId": "zakupki:123", "columnId": "workflowStatus", "value": "На решение"},
                    {"rowId": "zakupki:123", "columnId": "quantity", "value": "10,5"},
                    {"rowId": "zakupki:123", "columnId": "documentationPresent", "value": True},
                    {"rowId": "zakupki:123", "columnId": "certificateRequirements", "value": "ГОСТ 12.4"},
                ],
            }
        )
        record_operation = AsyncMock()

        with (
            patch(
                "app.services.procurement_grid_edits.get_or_create_grid_revision",
                AsyncMock(return_value=SimpleNamespace(dataset_version=5)),
            ),
            patch("app.services.procurement_grid_edits._find_record_by_row_id", AsyncMock(return_value=record)),
            patch("app.services.procurement_grid_edits.bump_procurement_lot_dataset_version", AsyncMock(return_value=6)),
            patch("app.services.procurement_grid_edits.clear_redo_grid_operations", AsyncMock(return_value=1)),
            patch("app.services.procurement_grid_edits.record_grid_operation", record_operation),
        ):
            response = await commit_procurement_lot_grid_edits(session, request, user_id="user-1", session_id="s-1")

        self.assertEqual(record.workflow_status, "decision")
        self.assertEqual(record.quantity, Decimal("10.5"))
        self.assertTrue(record.documentation_present)
        self.assertEqual(record.certificate_requirements, "ГОСТ 12.4")
        self.assertIn("decision", record.search_text or "")
        self.assertEqual(response.dataset_version, 6)
        self.assertEqual(response.updated_rows[0].id, "zakupki:123")
        self.assertEqual(response.updated_rows[0].row["workflowStatus"], "decision")
        self.assertEqual(response.updated_rows[0].row["quantity"], 10.5)
        self.assertTrue(response.updated_rows[0].row["documentationPresent"])
        self.assertEqual(response.updated_rows[0].row["certificateRequirements"], "ГОСТ 12.4")

        change_events = [item for item in session.added if isinstance(item, GridChangeEventModel)]
        self.assertEqual(len(change_events), 1)
        self.assertEqual(change_events[0].event_type, "row_updated")
        self.assertEqual(change_events[0].row_id, "zakupki:123")
        self.assertEqual(change_events[0].dataset_version, 6)
        self.assertEqual(
            change_events[0].payload["changed_fields"],
            ["certificate_requirements", "documentation_present", "quantity", "workflow_status"],
        )

        record_operation.assert_awaited_once()
        operation_kwargs = record_operation.await_args.kwargs
        self.assertEqual(operation_kwargs["table_id"], "procurement-lots")
        self.assertEqual(operation_kwargs["operation_type"], "edit")
        self.assertEqual(operation_kwargs["base_version"], 5)
        self.assertEqual(operation_kwargs["resulting_version"], 6)
        self.assertEqual(operation_kwargs["user_id"], "user-1")
        self.assertEqual(operation_kwargs["session_id"], "s-1")
        self.assertEqual(operation_kwargs["undo_payload"]["edits"][0]["value"], "new")
        self.assertEqual(operation_kwargs["redo_payload"]["edits"][1]["value"], "10.5")

    async def test_conflict_stops_before_loading_rows(self) -> None:
        request = ProcurementLotsGridEditRequest.model_validate(
            {"baseVersion": 4, "edits": [{"rowId": "zakupki:123", "columnId": "quantity", "value": 1}]}
        )
        find_record = AsyncMock()

        with (
            patch(
                "app.services.procurement_grid_edits.get_or_create_grid_revision",
                AsyncMock(return_value=SimpleNamespace(dataset_version=5)),
            ),
            patch("app.services.procurement_grid_edits._find_record_by_row_id", find_record),
        ):
            with self.assertRaises(ProcurementGridEditConflictError) as context:
                await commit_procurement_lot_grid_edits(FakeSession(), request)

        self.assertEqual(context.exception.current_version, 5)
        find_record.assert_not_awaited()

    async def test_router_maps_conflict_to_409_and_rolls_back(self) -> None:
        session = FakeSession()
        request = ProcurementLotsGridEditRequest.model_validate(
            {"baseVersion": 4, "edits": [{"rowId": "zakupki:123", "columnId": "quantity", "value": 1}]}
        )

        with patch(
            "app.api.procurement_lots_grid_router.commit_procurement_lot_grid_edits",
            AsyncMock(side_effect=ProcurementGridEditConflictError(base_version=4, current_version=5)),
        ):
            with self.assertRaises(HTTPException) as context:
                await commit_procurement_lots_edits(
                    request,
                    workspace_id=None,
                    grid_session_id=None,
                    session=session,
                    current_user=SimpleNamespace(id="user-1"),
                )

        self.assertEqual(context.exception.status_code, 409)
        self.assertEqual(session.rollback_count, 1)
        self.assertEqual(session.commit_count, 0)

    async def test_commit_edits_clears_redo_branch_for_scope(self) -> None:
        record = make_record()
        request = ProcurementLotsGridEditRequest.model_validate(
            {"baseVersion": 5, "edits": [{"rowId": "zakupki:123", "columnId": "quantity", "value": 1}]}
        )
        clear_redo = AsyncMock(return_value=2)

        with (
            patch(
                "app.services.procurement_grid_edits.get_or_create_grid_revision",
                AsyncMock(return_value=SimpleNamespace(dataset_version=5)),
            ),
            patch("app.services.procurement_grid_edits._find_record_by_row_id", AsyncMock(return_value=record)),
            patch("app.services.procurement_grid_edits.bump_procurement_lot_dataset_version", AsyncMock(return_value=6)),
            patch("app.services.procurement_grid_edits.clear_redo_grid_operations", clear_redo),
            patch("app.services.procurement_grid_edits.record_grid_operation", AsyncMock()),
        ):
            await commit_procurement_lot_grid_edits(
                FakeSession(),
                request,
                workspace_id="default",
                user_id="user-1",
                session_id="session-1",
            )

        clear_redo.assert_awaited_once_with(
            ANY,
            workspace_id="default",
            table_id="procurement-lots",
            user_id="user-1",
            session_id="session-1",
        )

    async def test_calculator_input_edit_recalculates_outputs(self) -> None:
        record = make_record()
        record.quantity = Decimal("100")
        record.unit_nmck = Decimal("1000")
        record.initial_price_value = Decimal("100000")
        record.calculator_inputs = {
            "fabric_consumption_per_unit": "2",
            "accessories_cost": "50",
            "sewing_cost": "100",
        }
        request = ProcurementLotsGridEditRequest.model_validate(
            {"baseVersion": 5, "edits": [{"rowId": "zakupki:123", "columnId": "fabricPrice", "value": "100"}]}
        )

        with (
            patch(
                "app.services.procurement_grid_edits.get_or_create_grid_revision",
                AsyncMock(return_value=SimpleNamespace(dataset_version=5)),
            ),
            patch("app.services.procurement_grid_edits._find_record_by_row_id", AsyncMock(return_value=record)),
            patch("app.services.procurement_grid_edits.bump_procurement_lot_dataset_version", AsyncMock(return_value=6)),
            patch("app.services.procurement_grid_edits.clear_redo_grid_operations", AsyncMock(return_value=1)),
            patch("app.services.procurement_grid_edits.record_grid_operation", AsyncMock()),
        ):
            response = await commit_procurement_lot_grid_edits(FakeSession(), request)

        self.assertEqual(record.calculator_inputs["fabric_price"], "100.00")
        self.assertIsNotNone(record.net_profit)
        self.assertEqual(response.updated_rows[0].row["calculatorInputs"]["fabric_price"], "100.00")
        self.assertTrue(response.updated_rows[0].row["calculatorScenarios"]["cautious"]["complete"])
        self.assertEqual(response.updated_rows[0].row["netProfit"], float(record.net_profit))

    def test_source_columns_are_not_editable(self) -> None:
        with self.assertRaisesRegex(ValueError, "not editable"):
            _procurement_field_for_column("registryNumber")

    def test_invalid_decimal_is_rejected(self) -> None:
        request = ProcurementLotsGridEditRequest.model_validate(
            {"baseVersion": 1, "edits": [{"rowId": "zakupki:123", "columnId": "quantity", "value": "abc"}]}
        )
        with self.assertRaisesRegex(ValueError, "must be a number"):
            request_edits = request.edits
            from app.services.procurement_grid_edits import _prepare_edit

            _prepare_edit(request_edits[0])

    def test_invalid_workflow_status_is_rejected(self) -> None:
        request = ProcurementLotsGridEditRequest.model_validate(
            {"baseVersion": 1, "edits": [{"rowId": "zakupki:123", "columnId": "workflowStatus", "value": "done"}]}
        )
        with self.assertRaisesRegex(ValueError, "workflow_status"):
            from app.services.procurement_grid_edits import _prepare_edit

            _prepare_edit(request.edits[0])


if __name__ == "__main__":
    unittest.main()
