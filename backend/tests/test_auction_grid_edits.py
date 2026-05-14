from __future__ import annotations

import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from affino_grid_backend import ApiException
from fastapi import HTTPException

from app.api.auction_lots_grid_router import commit_auction_lots_edits
from app.models.auction import AuctionLotRecord, AuctionLotWorkItem
from app.schemas.auction_grid import AuctionLotsGridEditRequest
from app.schemas.auctions import LotDatagridRow, LotFreshness, LotRating
from app.services.auction_grid_edits import (
    AuctionGridEditConflictError,
    _workspace_field_for_column,
    commit_auction_lot_grid_edits,
)


def make_record() -> AuctionLotRecord:
    row = LotDatagridRow(
        row_id="tbankrot:auction-1:lot-1",
        source="tbankrot",
        source_title="TBankrot",
        auction_id="auction-1",
        lot_id="lot-1",
        lot_name="Лот",
        status="Идет прием заявок",
        current_price="1 000 000 руб.",
        current_price_value=Decimal("1000000"),
        freshness=LotFreshness(is_new=True),
        rating=LotRating(score=10, level="low", reasons=[]),
    )
    return AuctionLotRecord(
        id=1,
        source_code="tbankrot",
        auction_external_id="auction-1",
        lot_external_id="lot-1",
        lot_name="Лот",
        status="Идет прием заявок",
        initial_price="1 000 000 руб.",
        content_hash="hash",
        datagrid_row=row.model_dump(mode="json"),
        normalized_item={"lot": {"name": "Лот", "status": "Идет прием заявок"}},
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


def runtime_config() -> SimpleNamespace:
    return SimpleNamespace(
        category_keywords={},
        exclusion_keywords=(),
        legal_risk_rules=None,
        owner_profile=None,
        dimension_weights=None,
    )


def apply_recalculated_row(record: AuctionLotRecord, detail_cache, work_item: AuctionLotWorkItem, **kwargs) -> None:
    row = dict(record.datagrid_row)
    row["market_value"] = str(work_item.market_value) if work_item.market_value is not None else None
    row["exclude_from_analysis"] = bool(work_item.exclude_from_analysis)
    record.datagrid_row = row


class AuctionGridEditsTests(unittest.IsolatedAsyncioTestCase):
    async def test_commit_edits_updates_work_item_revision_events_and_operation(self) -> None:
        record = make_record()
        row = dict(record.datagrid_row)
        row["market_value"] = "123.45"
        row["exclude_from_analysis"] = True
        record.datagrid_row = row
        session = FakeSession()
        request = AuctionLotsGridEditRequest.model_validate(
            {
                "baseVersion": 5,
                "edits": [
                    {"rowId": "tbankrot:auction-1:lot-1", "columnId": "marketValue", "value": "123.45"},
                    {"rowId": "tbankrot:auction-1:lot-1", "columnId": "excludeFromAnalysis", "value": True},
                ],
            }
        )

        with patch("app.services.grid_backend_edits.AuctionGridEditService") as service_type:
            service = service_type.return_value
            service.commit_edits = AsyncMock(
                return_value=SimpleNamespace(revision="6", rows=[SimpleNamespace(record=record)], rejected=[])
            )
            response = await commit_auction_lot_grid_edits(session, request, user_id="user-1", session_id="session-1")

        self.assertEqual(response.dataset_version, 6)
        self.assertEqual(response.updated_rows[0].id, "tbankrot:auction-1:lot-1")
        self.assertEqual(response.updated_rows[0].row.market_value, Decimal("123.45"))
        self.assertEqual(response.revision, "6")
        self.assertEqual(response.committed, [{"rowId": "tbankrot:auction-1:lot-1", "revision": "6"}])
        self.assertEqual(
            response.invalidation,
            {"type": "rows", "rowIds": ["tbankrot:auction-1:lot-1"], "reason": "edit"},
        )
        self.assertEqual(response.rows[0].id, "tbankrot:auction-1:lot-1")
        service_type.assert_called_once_with(workspace_id="default")
        service.commit_edits.assert_awaited_once()
        backend_request = service.commit_edits.await_args.args[1]
        self.assertEqual(backend_request.base_revision, "5")
        self.assertEqual(backend_request.base_version, 5)
        self.assertEqual(backend_request.user_id, "user-1")
        self.assertEqual(backend_request.session_id, "session-1")
        self.assertEqual(backend_request.payload["edits"][0]["rowId"], "tbankrot:auction-1:lot-1")

    async def test_package_edit_request_accepts_base_revision(self) -> None:
        record = make_record()
        request = AuctionLotsGridEditRequest.model_validate(
            {"baseRevision": "5", "edits": [{"rowId": "tbankrot:auction-1:lot-1", "columnId": "marketValue", "value": 1}]}
        )

        with patch("app.services.grid_backend_edits.AuctionGridEditService") as service_type:
            service_type.return_value.commit_edits = AsyncMock(
                return_value=SimpleNamespace(revision="6", rows=[SimpleNamespace(record=record)], rejected=[])
            )
            response = await commit_auction_lot_grid_edits(FakeSession(), request)

        self.assertEqual(request.base_version, 5)
        self.assertEqual(response.committed, [{"rowId": "tbankrot:auction-1:lot-1", "revision": "6"}])

    async def test_commit_edits_passes_scope_to_backend_adapter(self) -> None:
        record = make_record()
        request = AuctionLotsGridEditRequest.model_validate(
            {"baseVersion": 5, "edits": [{"rowId": "tbankrot:auction-1:lot-1", "columnId": "marketValue", "value": 1}]}
        )

        with patch("app.services.grid_backend_edits.AuctionGridEditService") as service_type:
            service_type.return_value.commit_edits = AsyncMock(
                return_value=SimpleNamespace(revision="6", rows=[SimpleNamespace(record=record)], rejected=[])
            )
            await commit_auction_lot_grid_edits(
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

    async def test_conflict_stops_before_loading_rows(self) -> None:
        request = AuctionLotsGridEditRequest.model_validate(
            {"baseVersion": 4, "edits": [{"rowId": "tbankrot:auction-1:lot-1", "columnId": "marketValue", "value": 1}]}
        )
        with (
            patch("app.services.grid_backend_edits.AuctionGridEditService") as service_type,
            patch("app.services.grid_state.get_dataset_version", AsyncMock(return_value=5)),
        ):
            service_type.return_value.commit_edits = AsyncMock(
                side_effect=ApiException(status_code=409, code="stale-revision", message="Edit commit revision is stale")
            )
            with self.assertRaises(AuctionGridEditConflictError) as context:
                await commit_auction_lot_grid_edits(FakeSession(), request)

        self.assertEqual(context.exception.current_version, 5)

    async def test_router_maps_conflict_to_409_and_rolls_back(self) -> None:
        session = FakeSession()
        request = AuctionLotsGridEditRequest.model_validate(
            {"baseVersion": 4, "edits": [{"rowId": "tbankrot:auction-1:lot-1", "columnId": "marketValue", "value": 1}]}
        )

        with patch(
            "app.api.auction_lots_grid_router.commit_auction_lot_grid_edits",
            AsyncMock(side_effect=AuctionGridEditConflictError(base_version=4, current_version=5)),
        ):
            with self.assertRaises(HTTPException) as context:
                await commit_auction_lots_edits(
                    request,
                    workspace_id=None,
                    grid_session_id=None,
                    session=session,
                    current_user=SimpleNamespace(id="user-1"),
                )

        self.assertEqual(context.exception.status_code, 409)
        self.assertEqual(session.rollback_count, 1)
        self.assertEqual(session.commit_count, 0)

    def test_source_columns_are_not_editable(self) -> None:
        with self.assertRaisesRegex(ValueError, "not editable"):
            _workspace_field_for_column("lotName")


if __name__ == "__main__":
    unittest.main()
