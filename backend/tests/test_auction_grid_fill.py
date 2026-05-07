from __future__ import annotations

import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.models.auction import AuctionLotRecord, AuctionLotWorkItem
from app.models.grid import GridChangeEventModel, GridOperationModel
from app.schemas.auction_grid import AuctionLotsGridFillRequest
from app.schemas.auctions import LotDatagridRow, LotFreshness, LotRating
from app.services.auction_grid_fill import commit_auction_lot_grid_fill


def make_record(row_id: str, market_value: Decimal | None) -> AuctionLotRecord:
    row = LotDatagridRow(
        row_id=row_id,
        source="tbankrot",
        source_title="TBankrot",
        auction_id="auction-1",
        lot_id=row_id.split(":")[-1],
        lot_name="Лот",
        status="Идет прием заявок",
        current_price="1 000 000 руб.",
        current_price_value=Decimal("1000000"),
        market_value=market_value,
        freshness=LotFreshness(is_new=True),
        rating=LotRating(score=10, level="low", reasons=[]),
    )
    return AuctionLotRecord(
        id=1 if row_id.endswith("lot-1") else 2 if row_id.endswith("lot-2") else 3,
        source_code="tbankrot",
        auction_external_id="auction-1",
        lot_external_id=row_id.split(":")[-1],
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

    async def execute(self, statement: object):
        return SimpleNamespace(rowcount=0)

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


def apply_recalculated_row(record: AuctionLotRecord, detail_cache, work_item: AuctionLotWorkItem, **kwargs) -> None:
    row = dict(record.datagrid_row)
    row["market_value"] = str(work_item.market_value) if work_item.market_value is not None else None
    record.datagrid_row = row


class AuctionGridFillTests(unittest.IsolatedAsyncioTestCase):
    async def test_copy_fill_applies_source_value_to_target_rows(self) -> None:
        source_record = make_record("tbankrot:auction-1:lot-1", Decimal("10"))
        target_one_record = make_record("tbankrot:auction-1:lot-2", Decimal("1"))
        target_two_record = make_record("tbankrot:auction-1:lot-3", Decimal("2"))

        source_row = LotDatagridRow.model_validate(source_record.datagrid_row)
        target_one_row = LotDatagridRow.model_validate(target_one_record.datagrid_row)
        target_two_row = LotDatagridRow.model_validate(target_two_record.datagrid_row)
        session = FakeSession()
        request = AuctionLotsGridFillRequest.model_validate(
            {
                "baseVersion": 5,
                "source": {"startRow": 0, "endRow": 1, "columnId": "marketValue"},
                "target": {"startRow": 1, "endRow": 3, "columnId": "marketValue"},
                "mode": "copy",
            }
        )
        target_one_work_item = AuctionLotWorkItem(lot_record_id=target_one_record.id, analogs=[], market_value=Decimal("1"))
        target_two_work_item = AuctionLotWorkItem(lot_record_id=target_two_record.id, analogs=[], market_value=Decimal("2"))

        def find_record_by_row_id(_: FakeSession, row_id: str):
            mapping = {
                "tbankrot:auction-1:lot-2": target_one_record,
                "tbankrot:auction-1:lot-3": target_two_record,
            }
            return mapping.get(row_id)

        def ensure_work_item(_: FakeSession, record: AuctionLotRecord):
            if record.id == target_one_record.id:
                return target_one_work_item
            return target_two_work_item

        with (
            patch(
                "app.services.auction_grid_fill.pull_persisted_lots_for_grid",
                AsyncMock(return_value=([(source_record, source_row), (target_one_record, target_one_row), (target_two_record, target_two_row)], 3)),
            ),
            patch(
                "app.services.auction_grid_edits.get_or_create_grid_revision",
                AsyncMock(return_value=SimpleNamespace(dataset_version=5)),
            ),
            patch("app.services.auction_grid_edits._find_record_by_row_id", side_effect=find_record_by_row_id),
            patch("app.services.auction_grid_edits.ensure_work_item", side_effect=ensure_work_item),
            patch(
                "app.services.auction_grid_edits.auction_analysis_config_service.get_runtime_config",
                AsyncMock(return_value=runtime_config()),
            ),
            patch("app.services.auction_grid_edits.recalculate_record_rating", side_effect=apply_recalculated_row),
            patch("app.services.auction_grid_edits.bump_dataset_version", AsyncMock(return_value=6)),
        ):
            response = await commit_auction_lot_grid_fill(
                session,
                request,
                user_id="user-1",
                session_id="session-1",
            )

        self.assertEqual(target_one_work_item.market_value, Decimal("10"))
        self.assertEqual(target_two_work_item.market_value, Decimal("10"))
        self.assertEqual(response.dataset_version, 6)
        self.assertEqual([row.row.market_value for row in response.updated_rows], [Decimal("10"), Decimal("10")])
        events = [item for item in session.added if isinstance(item, GridChangeEventModel)]
        self.assertEqual(len(events), 2)
        self.assertEqual({event.payload["source"] for event in events}, {"grid_edit"})
        operations = [item for item in session.added if isinstance(item, GridOperationModel)]
        self.assertEqual(len(operations), 1)
        self.assertEqual(operations[0].operation_type, "fill")


if __name__ == "__main__":
    unittest.main()
