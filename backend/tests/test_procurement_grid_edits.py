from __future__ import annotations

import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from affino_grid_backend import ApiException

from app.api.procurement_lots_grid_router import commit_procurement_lots_edits
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
        self.active_transaction = False

    async def scalar(self, statement: object) -> None:
        return None

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        self.flush_count += 1

    async def commit(self) -> None:
        self.commit_count += 1
        self.active_transaction = False

    async def rollback(self) -> None:
        self.rollback_count += 1

    def in_transaction(self) -> bool:
        return self.active_transaction


class ProcurementGridEditsTests(unittest.IsolatedAsyncioTestCase):
    async def test_commit_edits_updates_record_revision_events_operation_and_search_text(self) -> None:
        record = make_record()
        record.workflow_status = "decision"
        record.quantity = Decimal("10.5")
        record.documentation_present = True
        record.certificate_requirements = "ГОСТ 12.4"
        record.search_text = "decision ГОСТ 12.4"
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

        with patch("app.services.grid_backend_edits.ProcurementGridEditService") as service_type:
            service = service_type.return_value
            service.commit_edits = AsyncMock(
                return_value=SimpleNamespace(
                    revision="6",
                    rows=[record],
                    rejected=[],
                    committed=[
                        SimpleNamespace(row_id="zakupki:123", column_id="workflowStatus", revision="row-revision"),
                        SimpleNamespace(row_id="zakupki:123", column_id="quantity", revision="row-revision"),
                        SimpleNamespace(row_id="zakupki:123", column_id="documentationPresent", revision="row-revision"),
                        SimpleNamespace(row_id="zakupki:123", column_id="certificateRequirements", revision="row-revision"),
                    ],
                )
            )
            response = await commit_procurement_lot_grid_edits(session, request, user_id="user-1", session_id="s-1")

        self.assertIn("decision", record.search_text or "")
        self.assertEqual(response.dataset_version, 6)
        self.assertEqual(response.updated_rows[0].id, "zakupki:123")
        self.assertEqual(response.updated_rows[0].row["workflowStatus"], "decision")
        self.assertEqual(response.updated_rows[0].row["quantity"], 10.5)
        self.assertTrue(response.updated_rows[0].row["documentationPresent"])
        self.assertEqual(response.updated_rows[0].row["certificateRequirements"], "ГОСТ 12.4")
        self.assertEqual(response.revision, "6")
        self.assertEqual(
            response.committed,
            [
                {"rowId": "zakupki:123", "columnId": "workflowStatus", "revision": "6"},
                {"rowId": "zakupki:123", "columnId": "quantity", "revision": "6"},
                {"rowId": "zakupki:123", "columnId": "documentationPresent", "revision": "6"},
                {"rowId": "zakupki:123", "columnId": "certificateRequirements", "revision": "6"},
            ],
        )
        self.assertEqual(response.invalidation, {"type": "rows", "rowIds": ["zakupki:123"], "reason": "edit"})
        self.assertEqual(response.rows[0].id, "zakupki:123")

        service_type.assert_called_once_with(workspace_id="default")
        service.commit_edits.assert_awaited_once()
        backend_request = service.commit_edits.await_args.args[1]
        self.assertIsNone(backend_request.base_revision)
        self.assertEqual(backend_request.base_version, 5)
        self.assertEqual(backend_request.user_id, "user-1")
        self.assertEqual(backend_request.session_id, "s-1")
        self.assertEqual(backend_request.payload["edits"][0]["rowId"], "zakupki:123")

    async def test_package_edit_request_accepts_base_revision(self) -> None:
        record = make_record()
        request = ProcurementLotsGridEditRequest.model_validate(
            {"baseRevision": "5", "edits": [{"rowId": "zakupki:123", "columnId": "quantity", "value": 1}]}
        )

        with patch("app.services.grid_backend_edits.ProcurementGridEditService") as service_type:
            service_type.return_value.commit_edits = AsyncMock(
                return_value=SimpleNamespace(revision="6", rows=[record], rejected=[])
            )
            response = await commit_procurement_lot_grid_edits(FakeSession(), request)

        self.assertEqual(request.base_version, 5)
        self.assertEqual(response.committed, [{"rowId": "zakupki:123", "revision": "6"}])

    async def test_conflict_stops_before_loading_rows(self) -> None:
        request = ProcurementLotsGridEditRequest.model_validate(
            {"baseVersion": 4, "edits": [{"rowId": "zakupki:123", "columnId": "quantity", "value": 1}]}
        )
        with (
            patch("app.services.grid_backend_edits.ProcurementGridEditService") as service_type,
            patch("app.services.grid_state.get_dataset_version", AsyncMock(return_value=5)),
        ):
            service_type.return_value.commit_edits = AsyncMock(
                side_effect=ApiException(status_code=409, code="stale-revision", message="Edit commit revision is stale")
            )
            with self.assertRaises(ProcurementGridEditConflictError) as context:
                await commit_procurement_lot_grid_edits(FakeSession(), request)

        self.assertEqual(context.exception.current_version, 5)

    async def test_router_maps_conflict_to_409_and_rolls_back(self) -> None:
        session = FakeSession()
        request = ProcurementLotsGridEditRequest.model_validate(
            {"baseVersion": 4, "edits": [{"rowId": "zakupki:123", "columnId": "quantity", "value": 1}]}
        )

        with patch(
            "app.api.procurement_lots_grid_router.commit_procurement_lot_grid_edits",
            AsyncMock(side_effect=ProcurementGridEditConflictError(base_version=4, current_version=5)),
        ):
            response = await commit_procurement_lots_edits(
                request,
                workspace_id=None,
                grid_session_id=None,
                session=session,
                current_user=SimpleNamespace(id="user-1"),
            )

        self.assertEqual(response.dataset_version, 5)
        self.assertEqual(response.committed, [])
        self.assertEqual(response.rejected[0]["rowId"], "zakupki:123")
        self.assertEqual(response.rejected[0]["columnId"], "quantity")
        self.assertEqual(session.rollback_count, 1)
        self.assertEqual(session.commit_count, 0)

    async def test_commit_edits_passes_scope_to_backend_adapter(self) -> None:
        record = make_record()
        request = ProcurementLotsGridEditRequest.model_validate(
            {"baseVersion": 5, "edits": [{"rowId": "zakupki:123", "columnId": "quantity", "value": 1}]}
        )

        with patch("app.services.grid_backend_edits.ProcurementGridEditService") as service_type:
            service_type.return_value.commit_edits = AsyncMock(
                return_value=SimpleNamespace(revision="6", rows=[record], rejected=[])
            )
            await commit_procurement_lot_grid_edits(
                FakeSession(),
                request,
                workspace_id="default",
                user_id="user-1",
                session_id="session-1",
            )

        backend_request = service_type.return_value.commit_edits.await_args.args[1]
        self.assertEqual(backend_request.workspace_id, "default")
        self.assertEqual(backend_request.user_id, "user-1")
        self.assertEqual(backend_request.session_id, "session-1")

    async def test_commit_edits_closes_implicit_transaction_before_package_service(self) -> None:
        record = make_record()
        session = FakeSession()
        session.active_transaction = True
        request = ProcurementLotsGridEditRequest.model_validate(
            {"baseVersion": 5, "edits": [{"rowId": "zakupki:123", "columnId": "quantity", "value": 1}]}
        )

        with patch("app.services.grid_backend_edits.ProcurementGridEditService") as service_type:
            service_type.return_value.commit_edits = AsyncMock(
                return_value=SimpleNamespace(revision="6", rows=[record], rejected=[])
            )
            await commit_procurement_lot_grid_edits(session, request)

        self.assertEqual(session.commit_count, 1)
        self.assertFalse(session.active_transaction)
        service_type.return_value.commit_edits.assert_awaited_once()

    async def test_calculator_input_edit_recalculates_outputs(self) -> None:
        record = make_record()
        record.calculator_inputs = {
            "fabric_consumption_per_unit": "2",
            "accessories_cost": "50",
            "sewing_cost": "100",
            "fabric_price": "100.00",
        }
        record.net_profit = Decimal("1000")
        record.calculator_scenarios = {"cautious": {"complete": True}}
        request = ProcurementLotsGridEditRequest.model_validate(
            {"baseVersion": 5, "edits": [{"rowId": "zakupki:123", "columnId": "fabricPrice", "value": "100"}]}
        )

        with patch("app.services.grid_backend_edits.ProcurementGridEditService") as service_type:
            service_type.return_value.commit_edits = AsyncMock(
                return_value=SimpleNamespace(revision="6", rows=[record], rejected=[])
            )
            response = await commit_procurement_lot_grid_edits(FakeSession(), request)

        self.assertEqual(record.calculator_inputs["fabric_price"], "100.00")
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
