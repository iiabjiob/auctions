from __future__ import annotations

import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, patch

from fastapi import HTTPException

from app.api.auction_lots_grid_router import commit_auction_lots_edits
from app.models.auction import AuctionLotRecord, AuctionLotWorkItem
from app.models.grid import GridChangeEventModel
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
        work_item = AuctionLotWorkItem(lot_record_id=record.id, analogs=[], market_value=Decimal("10"))
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
        record_operation = AsyncMock()

        with (
            patch(
                "app.services.auction_grid_edits.get_or_create_grid_revision",
                AsyncMock(return_value=SimpleNamespace(dataset_version=5)),
            ),
            patch("app.services.auction_grid_edits._find_record_by_row_id", AsyncMock(return_value=record)),
            patch("app.services.auction_grid_edits.ensure_work_item", AsyncMock(return_value=work_item)),
            patch(
                "app.services.auction_grid_edits.auction_analysis_config_service.get_runtime_config",
                AsyncMock(return_value=runtime_config()),
            ),
            patch("app.services.auction_grid_edits.recalculate_record_rating", side_effect=apply_recalculated_row),
            patch("app.services.auction_grid_edits.bump_dataset_version", AsyncMock(return_value=6)),
            patch("app.services.auction_grid_edits.clear_redo_grid_operations", AsyncMock(return_value=1)),
            patch("app.services.auction_grid_edits.record_grid_operation", record_operation),
        ):
            response = await commit_auction_lot_grid_edits(session, request, user_id="user-1", session_id="session-1")

        self.assertEqual(work_item.market_value, Decimal("123.45"))
        self.assertTrue(work_item.exclude_from_analysis)
        self.assertEqual(response.dataset_version, 6)
        self.assertEqual(response.updated_rows[0].id, "tbankrot:auction-1:lot-1")
        self.assertEqual(response.updated_rows[0].row.market_value, Decimal("123.45"))
        change_events = [item for item in session.added if isinstance(item, GridChangeEventModel)]
        self.assertEqual(len(change_events), 1)
        self.assertEqual(change_events[0].event_type, "row_updated")
        self.assertEqual(change_events[0].row_id, "tbankrot:auction-1:lot-1")
        self.assertEqual(change_events[0].dataset_version, 6)
        self.assertEqual(change_events[0].payload["changed_fields"], ["exclude_from_analysis", "market_value"])
        record_operation.assert_awaited_once()
        operation_kwargs = record_operation.await_args.kwargs
        self.assertEqual(operation_kwargs["operation_type"], "edit")
        self.assertEqual(operation_kwargs["base_version"], 5)
        self.assertEqual(operation_kwargs["resulting_version"], 6)
        self.assertEqual(operation_kwargs["user_id"], "user-1")
        self.assertEqual(operation_kwargs["session_id"], "session-1")
        self.assertEqual(operation_kwargs["undo_payload"]["edits"][0]["value"], "10")

    async def test_commit_edits_clears_redo_branch_for_scope(self) -> None:
        record = make_record()
        work_item = AuctionLotWorkItem(lot_record_id=record.id, analogs=[])
        request = AuctionLotsGridEditRequest.model_validate(
            {"baseVersion": 5, "edits": [{"rowId": "tbankrot:auction-1:lot-1", "columnId": "marketValue", "value": 1}]}
        )
        clear_redo = AsyncMock(return_value=2)

        with (
            patch(
                "app.services.auction_grid_edits.get_or_create_grid_revision",
                AsyncMock(return_value=SimpleNamespace(dataset_version=5)),
            ),
            patch("app.services.auction_grid_edits._find_record_by_row_id", AsyncMock(return_value=record)),
            patch("app.services.auction_grid_edits.ensure_work_item", AsyncMock(return_value=work_item)),
            patch(
                "app.services.auction_grid_edits.auction_analysis_config_service.get_runtime_config",
                AsyncMock(return_value=runtime_config()),
            ),
            patch("app.services.auction_grid_edits.recalculate_record_rating", side_effect=apply_recalculated_row),
            patch("app.services.auction_grid_edits.bump_dataset_version", AsyncMock(return_value=6)),
            patch("app.services.auction_grid_edits.clear_redo_grid_operations", clear_redo),
            patch("app.services.auction_grid_edits.record_grid_operation", AsyncMock()),
        ):
            await commit_auction_lot_grid_edits(
                FakeSession(),
                request,
                workspace_id="default",
                user_id="user-1",
                session_id="session-1",
            )

        clear_redo.assert_awaited_once_with(
            ANY,
            workspace_id="default",
            table_id="auction-lots",
            user_id="user-1",
            session_id="session-1",
        )

    async def test_conflict_stops_before_loading_rows(self) -> None:
        request = AuctionLotsGridEditRequest.model_validate(
            {"baseVersion": 4, "edits": [{"rowId": "tbankrot:auction-1:lot-1", "columnId": "marketValue", "value": 1}]}
        )
        find_record = AsyncMock()

        with (
            patch(
                "app.services.auction_grid_edits.get_or_create_grid_revision",
                AsyncMock(return_value=SimpleNamespace(dataset_version=5)),
            ),
            patch("app.services.auction_grid_edits._find_record_by_row_id", find_record),
        ):
            with self.assertRaises(AuctionGridEditConflictError) as context:
                await commit_auction_lot_grid_edits(FakeSession(), request)

        self.assertEqual(context.exception.current_version, 5)
        find_record.assert_not_awaited()

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
