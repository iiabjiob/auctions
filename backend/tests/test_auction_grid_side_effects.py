from __future__ import annotations

import copy
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.models.auction import AuctionLotRecord, AuctionLotWorkItem
from app.schemas.auctions import (
    LotChangeSummary,
    LotDatagridRow,
    LotEconomyResponse,
    LotFreshness,
    LotRating,
    LotWorkItemResponse,
    LotWorkItemUpdate,
    LotWorkspaceResponse,
)
from app.services import auction_catalog
from app.services.auction_workspace import update_lot_work_item


def make_record() -> AuctionLotRecord:
    row = LotDatagridRow(
        row_id="tbankrot:auction-1:lot-1",
        source="tbankrot",
        source_title="TBankrot",
        auction_id="auction-1",
        auction_number="A-1",
        lot_id="lot-1",
        lot_number="1",
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
        auction_number="A-1",
        lot_number="1",
        lot_name="Лот",
        status="Идет прием заявок",
        initial_price="1 000 000 руб.",
        content_hash="hash",
        datagrid_row=row.model_dump(mode="json"),
        normalized_item={"lot": {"name": "Лот", "status": "Идет прием заявок"}},
    )


class FakeStatement:
    def offset(self, value: int) -> "FakeStatement":
        return self

    def limit(self, value: int) -> "FakeStatement":
        return self


class FakeScalars:
    def __init__(self, rows: list[AuctionLotRecord]) -> None:
        self._rows = rows

    def all(self) -> list[AuctionLotRecord]:
        return self._rows


class FakeCatalogSession:
    def __init__(self, rows: list[AuctionLotRecord]) -> None:
        self._rows = rows
        self.commit_count = 0

    async def scalars(self, statement: object) -> FakeScalars:
        return FakeScalars(self._rows)

    async def commit(self) -> None:
        self.commit_count += 1


class FakeWorkspaceSession:
    def __init__(self) -> None:
        self.commit_count = 0
        self.refresh_count = 0

    async def scalar(self, statement: object) -> None:
        return None

    async def commit(self) -> None:
        self.commit_count += 1

    async def refresh(self, value: object) -> None:
        self.refresh_count += 1


class AuctionGridSideEffectTests(unittest.IsolatedAsyncioTestCase):
    async def test_persisted_catalog_list_does_not_commit_or_mutate_rows(self) -> None:
        record = make_record()
        original_row = copy.deepcopy(record.datagrid_row)
        session = FakeCatalogSession([record])

        async def fake_count(session_arg: object, statement: object) -> int:
            return 1

        async def fake_empty_by_record_id(session_arg: object, record_ids: list[int]) -> dict:
            return {}

        with (
            patch.object(auction_catalog, "_build_persisted_lots_statement", return_value=FakeStatement()),
            patch.object(auction_catalog, "_apply_record_sort", side_effect=lambda statement, **kwargs: statement),
            patch.object(auction_catalog, "_count_persisted_lots", side_effect=fake_count),
            patch.object(auction_catalog, "_work_items_by_record_id", side_effect=fake_empty_by_record_id),
            patch.object(auction_catalog, "_detail_caches_by_record_id", side_effect=fake_empty_by_record_id),
        ):
            response = await auction_catalog.list_persisted_lots_for_datagrid(session, source="tbankrot")

        self.assertEqual(response.total, 1)
        self.assertEqual(session.commit_count, 0)
        self.assertEqual(record.datagrid_row, original_row)

    async def test_workspace_update_bumps_grid_revision_with_changed_fields(self) -> None:
        record = make_record()
        work_item = AuctionLotWorkItem(lot_record_id=record.id, analogs=[])
        session = FakeWorkspaceSession()
        workspace_response = LotWorkspaceResponse(
            record_id=record.id,
            row=LotDatagridRow.model_validate(record.datagrid_row),
            work_item=LotWorkItemResponse(lot_record_id=record.id),
            economy=LotEconomyResponse(),
            changes=LotChangeSummary(),
        )
        runtime_config = SimpleNamespace(
            category_keywords={},
            exclusion_keywords=(),
            legal_risk_rules=None,
            owner_profile=None,
            dimension_weights=None,
        )
        bump = AsyncMock(return_value=1)

        with (
            patch("app.services.auction_workspace.find_lot_record", AsyncMock(return_value=record)),
            patch("app.services.auction_workspace.ensure_work_item", AsyncMock(return_value=work_item)),
            patch("app.services.auction_workspace.auction_analysis_config_service.get_runtime_config", AsyncMock(return_value=runtime_config)),
            patch("app.services.auction_workspace.recalculate_record_rating"),
            patch("app.services.auction_workspace.bump_auction_lot_dataset_version", bump),
            patch("app.services.auction_workspace._publish_row_updated", AsyncMock()),
            patch("app.services.auction_workspace.build_workspace_response", AsyncMock(return_value=workspace_response)),
        ):
            result = await update_lot_work_item(
                session,
                source="tbankrot",
                lot_id="lot-1",
                auction_id="auction-1",
                payload=LotWorkItemUpdate(comment="ok", decision_status="watch"),
            )

        self.assertEqual(result.record_id, record.id)
        self.assertEqual(session.commit_count, 1)
        bump.assert_awaited_once()
        _, bump_record = bump.await_args.args
        self.assertIs(bump_record, record)
        self.assertEqual(bump.await_args.kwargs["event_type"], "row_updated")
        self.assertEqual(
            bump.await_args.kwargs["payload"],
            {"source": "workspace_update", "changed_fields": ["comment", "decision_status"]},
        )


if __name__ == "__main__":
    unittest.main()
