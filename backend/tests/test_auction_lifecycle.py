from __future__ import annotations

import unittest
from datetime import UTC, datetime
from decimal import Decimal

from app.models.auction import AuctionLotDetailCache, AuctionLotRecord, AuctionLotWorkItem
from app.schemas.auctions import LotDatagridRow, LotFreshness, LotRating
from app.services.auction_lifecycle import (
    LotLifecycleState,
    is_terminal_lifecycle_state,
    lot_is_active,
    lot_is_discovered,
    lot_is_enriched,
    lot_is_list_synced,
    lot_is_scored,
    lot_is_stale,
    lot_needs_enrichment,
    lot_needs_scoring,
)
from app.services.auction_scoring import build_record_score_input_hash, recalculate_record_rating


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
        rating=LotRating(score=0, level="low", reasons=[]),
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


def make_detail_cache() -> AuctionLotDetailCache:
    return AuctionLotDetailCache(
        lot_record_id=1,
        content_hash="detail-hash",
        lot_detail={"lot": {"description": "Описание"}},
        auction_detail=None,
        documents=[{"name": "photo.jpg"}],
    )


def make_work_item() -> AuctionLotWorkItem:
    return AuctionLotWorkItem(
        lot_record_id=1,
        analogs=[],
        market_value=Decimal("2000000"),
        target_profit=Decimal("300000"),
    )


class AuctionLifecycleTests(unittest.TestCase):
    def test_lifecycle_states_are_stable_and_stringified(self) -> None:
        self.assertEqual(
            [state.value for state in LotLifecycleState],
            [
                "discovered",
                "list_synced",
                "needs_enrichment",
                "enriched",
                "scored",
                "active",
                "stale",
                "archived",
            ],
        )

    def test_terminal_state_detection_is_conservative(self) -> None:
        self.assertTrue(is_terminal_lifecycle_state(LotLifecycleState.ARCHIVED))
        self.assertFalse(is_terminal_lifecycle_state(LotLifecycleState.STALE))
        self.assertFalse(is_terminal_lifecycle_state(LotLifecycleState.ACTIVE))

    def test_local_processing_predicates_follow_persisted_state(self) -> None:
        record = make_record()
        detail_cache = make_detail_cache()
        work_item = make_work_item()

        self.assertTrue(lot_is_discovered(record))
        self.assertTrue(lot_is_list_synced(record))
        self.assertTrue(lot_needs_enrichment(record))
        self.assertFalse(lot_is_enriched(record))
        self.assertTrue(lot_needs_scoring(record))
        self.assertFalse(lot_is_scored(record))
        self.assertFalse(lot_is_active(record))
        self.assertTrue(lot_is_stale(record))

        recalculate_record_rating(record, detail_cache, work_item)
        input_hash = build_record_score_input_hash(record, detail_cache, work_item)

        self.assertFalse(lot_needs_enrichment(record, detail_cache))
        self.assertTrue(lot_is_enriched(record, detail_cache))
        self.assertFalse(lot_needs_scoring(record, input_hash=input_hash))
        self.assertTrue(lot_is_scored(record, input_hash=input_hash))
        self.assertTrue(lot_is_active(record, detail_cache=detail_cache, input_hash=input_hash))
        self.assertFalse(lot_is_stale(record, input_hash=input_hash))

        record.scoring_version = "old-version"
        self.assertTrue(lot_needs_scoring(record, input_hash=input_hash))
        self.assertTrue(lot_is_stale(record, input_hash=input_hash))
        self.assertFalse(lot_is_active(record, detail_cache=detail_cache, input_hash=input_hash))

    def test_lot_record_has_actuality_columns_and_default_status(self) -> None:
        column_names = set(AuctionLotRecord.__table__.columns.keys())
        self.assertTrue(
            {
                "publication_at",
                "application_start_at",
                "application_deadline_at",
                "auction_at",
                "finished_at",
                "lifecycle_status",
                "archived_at",
                "archive_reason",
                "actuality_checked_at",
            }.issubset(column_names)
        )
        self.assertEqual(AuctionLotRecord.__table__.c.lifecycle_status.default.arg, "active")
        self.assertTrue(AuctionLotRecord.__table__.c.lifecycle_status.nullable is False)


if __name__ == "__main__":
    unittest.main()
