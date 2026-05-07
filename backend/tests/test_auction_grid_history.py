from __future__ import annotations

import unittest
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.models.auction import AuctionLotRecord, AuctionLotWorkItem
from app.models.grid import GridChangeEventModel, GridOperationModel
from app.schemas.auctions import LotDatagridRow, LotFreshness, LotRating
from app.services.auction_grid_history import (
    get_auction_lot_grid_history_status,
    redo_auction_lot_grid_history,
    undo_auction_lot_grid_history,
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
        market_value=Decimal("123.45"),
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

    async def scalar(self, statement: object) -> None:
        return None

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        self.flush_count += 1


def runtime_config() -> SimpleNamespace:
    return SimpleNamespace(
        category_keywords={},
        exclusion_keywords=(),
        legal_risk_rules=None,
        owner_profile=None,
        dimension_weights=None,
    )


def make_operation(*, undone: bool = False) -> GridOperationModel:
    return GridOperationModel(
        id=uuid4(),
        workspace_id="default",
        table_id="auction-lots",
        user_id="user-1",
        session_id="session-1",
        operation_type="edit",
        base_version=5,
        resulting_version=6,
        payload={
            "edits": [{"rowId": "tbankrot:auction-1:lot-1", "columnId": "marketValue", "value": "123.45"}]
        },
        undo_payload={
            "edits": [
                {
                    "rowId": "tbankrot:auction-1:lot-1",
                    "columnId": "marketValue",
                    "field": "market_value",
                    "value": "10",
                }
            ]
        },
        redo_payload={
            "edits": [
                {
                    "rowId": "tbankrot:auction-1:lot-1",
                    "columnId": "marketValue",
                    "field": "market_value",
                    "value": "123.45",
                }
            ]
        },
        undone_at=datetime.now(UTC) if undone else None,
    )


def apply_recalculated_row(record: AuctionLotRecord, detail_cache, work_item: AuctionLotWorkItem, **kwargs) -> None:
    row = dict(record.datagrid_row)
    row["market_value"] = str(work_item.market_value) if work_item.market_value is not None else None
    record.datagrid_row = row


class AuctionGridHistoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_undo_restores_previous_value_and_writes_change_event(self) -> None:
        record = make_record()
        work_item = AuctionLotWorkItem(lot_record_id=record.id, analogs=[], market_value=Decimal("123.45"))
        operation = make_operation()
        session = FakeSession()

        with (
            patch("app.services.auction_grid_history._find_history_operation", AsyncMock(return_value=operation)),
            patch("app.services.auction_grid_history._find_record_by_row_id", AsyncMock(return_value=record)),
            patch("app.services.auction_grid_history.ensure_work_item", AsyncMock(return_value=work_item)),
            patch(
                "app.services.auction_grid_history.auction_analysis_config_service.get_runtime_config",
                AsyncMock(return_value=runtime_config()),
            ),
            patch("app.services.auction_grid_history.recalculate_record_rating", side_effect=apply_recalculated_row),
            patch("app.services.auction_grid_history.bump_dataset_version", AsyncMock(return_value=7)),
        ):
            response = await undo_auction_lot_grid_history(
                session,
                table_id="auction-lots",
                user_id="user-1",
                session_id="session-1",
            )

        self.assertEqual(work_item.market_value, Decimal("10"))
        self.assertIsNotNone(operation.undone_at)
        self.assertEqual(response.dataset_version, 7)
        self.assertEqual(response.updated_rows[0].row.market_value, Decimal("10"))
        events = [item for item in session.added if isinstance(item, GridChangeEventModel)]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, "row_updated")
        self.assertEqual(events[0].row_id, "tbankrot:auction-1:lot-1")
        self.assertEqual(events[0].payload["source"], "history_undo")
        self.assertEqual(events[0].payload["changed_fields"], ["market_value"])

    async def test_redo_reapplies_value_and_clears_undone_at(self) -> None:
        record = make_record()
        record.datagrid_row["market_value"] = "10"
        work_item = AuctionLotWorkItem(lot_record_id=record.id, analogs=[], market_value=Decimal("10"))
        operation = make_operation(undone=True)
        session = FakeSession()

        with (
            patch("app.services.auction_grid_history._find_history_operation", AsyncMock(return_value=operation)),
            patch("app.services.auction_grid_history._find_record_by_row_id", AsyncMock(return_value=record)),
            patch("app.services.auction_grid_history.ensure_work_item", AsyncMock(return_value=work_item)),
            patch(
                "app.services.auction_grid_history.auction_analysis_config_service.get_runtime_config",
                AsyncMock(return_value=runtime_config()),
            ),
            patch("app.services.auction_grid_history.recalculate_record_rating", side_effect=apply_recalculated_row),
            patch("app.services.auction_grid_history.bump_dataset_version", AsyncMock(return_value=8)),
        ):
            response = await redo_auction_lot_grid_history(
                session,
                table_id="auction-lots",
                user_id="user-1",
                session_id="session-1",
            )

        self.assertEqual(work_item.market_value, Decimal("123.45"))
        self.assertIsNone(operation.undone_at)
        self.assertEqual(response.dataset_version, 8)
        self.assertEqual(response.updated_rows[0].row.market_value, Decimal("123.45"))
        events = [item for item in session.added if isinstance(item, GridChangeEventModel)]
        self.assertEqual(events[0].payload["source"], "history_redo")

    async def test_status_reflects_undo_and_redo_availability(self) -> None:
        with patch("app.services.auction_grid_history._has_history_operation", AsyncMock(side_effect=[True, False])):
            response = await get_auction_lot_grid_history_status(
                FakeSession(),
                table_id="auction-lots",
                user_id="user-1",
                session_id="session-1",
            )

        self.assertTrue(response.can_undo)
        self.assertFalse(response.can_redo)
        self.assertEqual(response.model_dump(by_alias=True), {"canUndo": True, "canRedo": False})

    async def test_empty_undo_returns_current_version_without_rows(self) -> None:
        with (
            patch("app.services.auction_grid_history._find_history_operation", AsyncMock(return_value=None)),
            patch("app.services.auction_grid_history.get_dataset_version", AsyncMock(return_value=9)),
        ):
            response = await undo_auction_lot_grid_history(FakeSession(), table_id="auction-lots", user_id="user-1")

        self.assertEqual(response.dataset_version, 9)
        self.assertEqual(response.updated_rows, [])

    async def test_unknown_table_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "auction-lots"):
            await get_auction_lot_grid_history_status(FakeSession(), table_id="other", user_id="user-1")


if __name__ == "__main__":
    unittest.main()
