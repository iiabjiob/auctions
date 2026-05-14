from __future__ import annotations

import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.api.procurement_lots_grid_router import commit_procurement_lots_fill
from app.models.procurement import ProcurementLotRecord
from app.schemas.procurement_grid import ProcurementLotsGridFillRequest
from app.services.procurement_grid_fill import commit_procurement_lot_grid_fill


def make_record(record_id: int, external_id: str, quantity: Decimal | None) -> ProcurementLotRecord:
    return ProcurementLotRecord(
        id=record_id,
        source_code="zakupki",
        external_id=external_id,
        registry_number=external_id,
        title="Поставка",
        content_hash="hash",
        workflow_status="new",
        quantity=quantity,
        matched_keywords=[],
        excluded_keywords=[],
        attractiveness_score=0,
        attractiveness_level="low",
        attractiveness_reasons=[],
        calculator_inputs={},
        calculator_scenarios={},
        normalized_item={},
        raw_item={},
    )


class FakeSession:
    def __init__(self) -> None:
        self.commit_count = 0
        self.rollback_count = 0

    async def commit(self) -> None:
        self.commit_count += 1

    async def rollback(self) -> None:
        self.rollback_count += 1


class ProcurementGridFillTests(unittest.IsolatedAsyncioTestCase):
    async def test_copy_fill_builds_package_request_from_ranges(self) -> None:
        source_record = make_record(1, "source", Decimal("10"))
        target_one = make_record(2, "target-1", Decimal("1"))
        target_two = make_record(3, "target-2", Decimal("2"))
        request = ProcurementLotsGridFillRequest.model_validate(
            {
                "baseVersion": 5,
                "source": {"startRow": 0, "endRow": 1, "columnId": "quantity"},
                "target": {"startRow": 1, "endRow": 3, "columnId": "quantity"},
                "mode": "copy",
            }
        )

        with (
            patch(
                "app.services.procurement_grid_fill.pull_procurement_lots_for_grid",
                AsyncMock(
                    return_value=(
                        [
                            (source_record, {"quantity": 10.0}),
                            (target_one, {"quantity": 1.0}),
                            (target_two, {"quantity": 2.0}),
                        ],
                        3,
                    )
                ),
            ),
            patch("app.services.grid_backend_fill.ProcurementGridFillService") as service_type,
        ):
            service_type.return_value.commit_fill = AsyncMock(
                return_value=SimpleNamespace(revision="6", rows=[target_one, target_two])
            )
            response = await commit_procurement_lot_grid_fill(
                FakeSession(),
                request,
                user_id="user-1",
                session_id="session-1",
            )

        self.assertEqual(response.dataset_version, 6)
        self.assertEqual([row.id for row in response.updated_rows], ["zakupki:target-1", "zakupki:target-2"])
        backend_request = service_type.return_value.commit_fill.await_args.args[1]
        self.assertEqual(backend_request.mode, "copy")
        self.assertEqual(backend_request.base_version, 5)
        self.assertEqual(backend_request.source_row_ids, ["zakupki:source"])
        self.assertEqual(backend_request.target_row_ids, ["zakupki:target-1", "zakupki:target-2"])
        self.assertEqual(backend_request.fill_columns, ["quantity"])
        self.assertEqual([edit["rowId"] for edit in backend_request.metadata["edits"]], ["zakupki:target-1", "zakupki:target-2"])

    async def test_router_maps_fill_conflict_to_409_and_rolls_back(self) -> None:
        session = FakeSession()
        request = ProcurementLotsGridFillRequest.model_validate(
            {
                "baseVersion": 4,
                "source": {"startRow": 0, "endRow": 1, "columnId": "quantity"},
                "target": {"startRow": 1, "endRow": 2, "columnId": "quantity"},
                "mode": "copy",
            }
        )

        from app.services.procurement_grid_edits import ProcurementGridEditConflictError

        with patch(
            "app.api.procurement_lots_grid_router.commit_procurement_lot_grid_fill",
            AsyncMock(side_effect=ProcurementGridEditConflictError(base_version=4, current_version=5)),
        ):
            with self.assertRaises(HTTPException) as context:
                await commit_procurement_lots_fill(
                    request,
                    workspace_id=None,
                    grid_session_id=None,
                    session=session,
                    current_user=SimpleNamespace(id="user-1"),
                )

        self.assertEqual(context.exception.status_code, 409)
        self.assertEqual(session.rollback_count, 1)
        self.assertEqual(session.commit_count, 0)


if __name__ == "__main__":
    unittest.main()
