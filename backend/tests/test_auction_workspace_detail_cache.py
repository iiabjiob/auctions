from __future__ import annotations

import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from app.models.auction import AuctionLotDetailCache, AuctionLotRecord
from app.services.auction_workspace import (
    _detail_cache_has_price_schedule,
    _bounded_detail_payload,
    _lot_detail_response_from_cache,
    _lot_detail_payload_with_price_schedule_state,
    ensure_lot_detail_cache,
    get_cached_lot_detail_cache,
)


class FakeSession:
    def __init__(self, detail_cache=None):
        self.detail_cache = detail_cache

    async def scalar(self, statement):
        return self.detail_cache


class ForbiddenDetailProvider:
    def get_lot(self, lot_id: str, *, include_price_schedule: bool = True):
        raise HTTPError(f"https://example.test/{lot_id}", 403, "Forbidden", hdrs=None, fp=None)


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

    def test_workspace_detail_payload_is_bounded_for_browser_rendering(self) -> None:
        payload = {
            "lot": {
                "description": "x" * 5000,
                "price_schedule": [{"starts_at": str(index), "price": str(index)} for index in range(200)],
            },
            "documents": [{"name": str(index)} for index in range(200)],
            "raw_fields": [{"name": str(index), "value": "y" * 5000} for index in range(200)],
            "raw_tables": [[str(index)] for index in range(40)],
        }

        bounded = _bounded_detail_payload(payload)

        self.assertLessEqual(len(bounded["lot"]["price_schedule"]), 120)
        self.assertLessEqual(len(bounded["documents"]), 160)
        self.assertLessEqual(len(bounded["raw_fields"]), 160)
        self.assertLessEqual(len(bounded["raw_tables"]), 20)
        self.assertLessEqual(len(bounded["lot"]["description"]), 4003)
        self.assertLessEqual(len(bounded["raw_fields"][0]["value"]), 4003)


class AuctionWorkspaceDetailFetchTests(unittest.IsolatedAsyncioTestCase):
    async def test_detail_fetch_403_without_cache_degrades_to_empty_detail(self) -> None:
        record = AuctionLotRecord(
            id=1,
            source_code="tbankrot",
            auction_external_id="auction-1",
            lot_external_id="lot-1",
            content_hash="hash",
            datagrid_row={},
            normalized_item={},
        )

        with patch("app.services.auction_workspace.get_source_provider", return_value=ForbiddenDetailProvider()):
            detail_cache = await ensure_lot_detail_cache(FakeSession(), record)

        self.assertIsNone(detail_cache)

    async def test_detail_fetch_403_preserves_existing_cache(self) -> None:
        record = AuctionLotRecord(
            id=1,
            source_code="tbankrot",
            auction_external_id="auction-1",
            lot_external_id="lot-1",
            content_hash="hash",
            datagrid_row={},
            normalized_item={},
        )
        existing_cache = AuctionLotDetailCache(
            lot_record_id=1,
            content_hash="hash",
            lot_detail={"lot": {"price_schedule": []}, "_price_schedule_loaded": False},
            auction_detail=None,
            documents=[],
        )

        with patch("app.services.auction_workspace.get_source_provider", return_value=ForbiddenDetailProvider()):
            detail_cache = await ensure_lot_detail_cache(FakeSession(existing_cache), record)

        self.assertIs(detail_cache, existing_cache)

    async def test_cached_detail_lookup_does_not_fetch_source(self) -> None:
        record = AuctionLotRecord(
            id=1,
            source_code="tbankrot",
            auction_external_id="auction-1",
            lot_external_id="lot-1",
            content_hash="hash",
            datagrid_row={},
            normalized_item={},
        )
        existing_cache = AuctionLotDetailCache(
            lot_record_id=1,
            content_hash="hash",
            lot_detail={"lot": {"price_schedule": []}, "_price_schedule_loaded": False},
            auction_detail=None,
            documents=[],
        )

        with patch("app.services.auction_workspace.get_source_provider") as get_source_provider:
            detail_cache = await get_cached_lot_detail_cache(FakeSession(existing_cache), record)

        self.assertIs(detail_cache, existing_cache)
        get_source_provider.assert_not_called()


if __name__ == "__main__":
    unittest.main()
