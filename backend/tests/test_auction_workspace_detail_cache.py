from __future__ import annotations

import unittest

from app.models.auction import AuctionLotDetailCache, AuctionLotRecord
from app.services.auction_workspace import (
    _detail_cache_has_price_schedule,
    _lot_detail_response_from_cache,
    _lot_detail_payload_with_price_schedule_state,
)


class AuctionWorkspaceDetailCacheTests(unittest.TestCase):
    def test_cache_without_schedule_is_not_treated_as_loaded(self) -> None:
        cache = AuctionLotDetailCache(
            lot_record_id=1,
            content_hash="hash",
            lot_detail={"lot": {"price_schedule": []}, "_price_schedule_loaded": False},
            auction_detail=None,
            documents=[],
        )

        self.assertFalse(_detail_cache_has_price_schedule(cache))

    def test_cache_with_loaded_empty_schedule_is_treated_as_loaded(self) -> None:
        cache = AuctionLotDetailCache(
            lot_record_id=1,
            content_hash="hash",
            lot_detail={"lot": {"price_schedule": []}, "_price_schedule_loaded": True},
            auction_detail=None,
            documents=[],
        )

        self.assertTrue(_detail_cache_has_price_schedule(cache))

    def test_background_refresh_preserves_existing_price_schedule(self) -> None:
        previous_payload = {
            "lot": {"price_schedule": [{"starts_at": "01.01.2026", "price": "1 000 000 руб."}]},
            "_price_schedule_loaded": True,
        }
        next_payload = _lot_detail_payload_with_price_schedule_state(
            {"lot": {"price_schedule": []}},
            previous_payload=previous_payload,
            include_price_schedule=False,
        )

        self.assertTrue(next_payload["_price_schedule_loaded"])
        self.assertEqual(next_payload["lot"]["price_schedule"], previous_payload["lot"]["price_schedule"])

    def test_interactive_detail_marks_price_schedule_as_loaded(self) -> None:
        next_payload = _lot_detail_payload_with_price_schedule_state(
            {"lot": {"price_schedule": []}},
            previous_payload=None,
            include_price_schedule=True,
        )

        self.assertTrue(next_payload["_price_schedule_loaded"])

    def test_interactive_detail_preserves_fallback_schedule_when_source_returns_empty_schedule(self) -> None:
        fallback_schedule = [{"starts_at": "01.01.2026", "price": "1 000 000 руб."}]
        next_payload = _lot_detail_payload_with_price_schedule_state(
            {"lot": {"price_schedule": []}},
            previous_payload=None,
            include_price_schedule=True,
            fallback_price_schedule=fallback_schedule,
        )

        self.assertTrue(next_payload["_price_schedule_loaded"])
        self.assertEqual(next_payload["lot"]["price_schedule"], fallback_schedule)

    def test_workspace_detail_response_hydrates_empty_cache_schedule_from_row(self) -> None:
        fallback_schedule = [{"starts_at": "01.01.2026", "price": "1 000 000 руб."}]
        record = AuctionLotRecord(
            id=1,
            source_code="tbankrot",
            auction_external_id="auction-1",
            lot_external_id="lot-1",
            content_hash="hash",
            datagrid_row={"price_schedule": fallback_schedule},
            normalized_item={},
        )
        cache = AuctionLotDetailCache(
            lot_record_id=1,
            content_hash="hash",
            lot_detail={
                "source": "tbankrot",
                "url": "https://tbankrot.ru/item?id=lot-1",
                "auction": {},
                "lot": {"price_schedule": []},
                "documents": [],
                "raw_fields": [],
                "raw_tables": [],
                "_price_schedule_loaded": True,
            },
            auction_detail=None,
            documents=[],
        )

        response = _lot_detail_response_from_cache(record, cache)

        self.assertIsNotNone(response)
        self.assertEqual(response.lot.price_schedule[0].starts_at, "01.01.2026")


if __name__ == "__main__":
    unittest.main()