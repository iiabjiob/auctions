from __future__ import annotations

import hashlib
import json
import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.error import HTTPError

from app.models.auction import AuctionLotDetailCache, AuctionLotRecord
from app.schemas.auctions import AuctionSummary, LotDetailResponse, LotImage, LotSummary
from app.services.auction_scoring import invalidate_lot_score
from app.services.auction_workspace import (
    _detail_cache_has_price_schedule,
    _bounded_detail_payload,
    _lot_detail_response_from_cache,
    _lot_detail_payload_with_price_schedule_state,
    get_lot_workspace,
    ensure_lot_detail_cache,
    get_cached_lot_detail_cache,
    refresh_lot_workspace_live,
)


class FakeSession:
    def __init__(self, detail_cache=None):
        self.detail_cache = detail_cache
        self.added = []
        self.commits = 0

    async def scalar(self, statement):
        return self.detail_cache

    def add(self, item) -> None:
        self.added.append(item)

    async def flush(self):
        return None

    async def commit(self):
        self.commits += 1


class ForbiddenDetailProvider:
    def get_lot(self, lot_id: str, *, include_price_schedule: bool = True):
        raise HTTPError(f"https://example.test/{lot_id}", 403, "Forbidden", hdrs=None, fp=None)


class StaticDetailProvider:
    code = "tbankrot"
    title = "TBankrot"
    website = "https://tbankrot.ru"

    def __init__(self, lot_response: LotDetailResponse):
        self.lot_response = lot_response
        self.include_price_schedule_calls: list[bool] = []

    def info(self):
        return None

    def get_lot(self, lot_id: str, *, include_price_schedule: bool = True):
        self.include_price_schedule_calls.append(include_price_schedule)
        return self.lot_response

    def get_auction(self, auction_id: str):
        raise NotImplementedError("Auction details are not needed for this test")

    def get_auction_publication_date(self, auction_id: str):
        return None


def _lot_detail_content_hash(response: LotDetailResponse) -> str:
    payload = _lot_detail_payload_with_price_schedule_state(
        response.model_dump(mode="json"),
        previous_payload=None,
        include_price_schedule=False,
    )
    data = {"lot_detail": payload, "auction_detail": None, "documents": response.documents}
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _runtime_config() -> SimpleNamespace:
    return SimpleNamespace(
        category_keywords={},
        exclusion_keywords=(),
        legal_risk_rules=SimpleNamespace(),
        owner_profile=SimpleNamespace(),
        dimension_weights=SimpleNamespace(),
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

    def test_workspace_detail_response_preserves_cached_lot_images(self) -> None:
        record = AuctionLotRecord(
            id=1,
            source_code="tbankrot",
            auction_external_id="auction-1",
            lot_external_id="lot-1",
            content_hash="hash",
            datagrid_row={},
            normalized_item={},
        )
        cache = AuctionLotDetailCache(
            lot_record_id=1,
            content_hash="hash",
            lot_detail={
                "source": "tbankrot",
                "url": "https://tbankrot.ru/item?id=lot-1",
                "auction": {},
                "lot": {
                    "images": [
                        LotImage(
                            url="https://tbankrot.ru/upload/lot/photo.jpg",
                            thumbnail_url="https://tbankrot.ru/upload/lot/photo-thumb.jpg",
                            alt="Фото лота",
                            source="tbankrot",
                        ).model_dump(mode="json")
                    ],
                    "primary_image_url": "https://tbankrot.ru/upload/lot/photo.jpg",
                },
                "documents": [],
                "raw_fields": [],
                "raw_tables": [],
            },
            auction_detail=None,
            documents=[],
        )

        response = _lot_detail_response_from_cache(record, cache)

        self.assertIsNotNone(response)
        self.assertEqual(response.lot.primary_image_url, "https://tbankrot.ru/upload/lot/photo.jpg")
        self.assertEqual(response.lot.images[0].url, "https://tbankrot.ru/upload/lot/photo.jpg")

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

    async def test_workspace_open_uses_cached_detail_without_source_refresh(self) -> None:
        record = AuctionLotRecord(
            id=1,
            source_code="tbankrot",
            auction_external_id="auction-1",
            lot_external_id="lot-1",
            content_hash="hash",
            datagrid_row={},
            normalized_item={},
        )
        detail_cache = AuctionLotDetailCache(
            lot_record_id=1,
            content_hash="hash",
            lot_detail={"lot": {"price_schedule": []}, "_price_schedule_loaded": False},
            auction_detail=None,
            documents=[],
        )
        session = FakeSession(detail_cache)
        workspace = SimpleNamespace(marker="workspace")

        with (
            patch("app.services.auction_workspace.find_lot_record", AsyncMock(return_value=record)),
            patch("app.services.auction_workspace.get_cached_lot_detail_cache", AsyncMock(return_value=detail_cache)) as get_cached_detail,
            patch("app.services.auction_workspace.ensure_lot_detail_cache", AsyncMock()) as refresh_detail,
            patch("app.services.auction_workspace.ensure_work_item", AsyncMock(return_value=SimpleNamespace(lot_record_id=1))),
            patch("app.services.auction_workspace.build_workspace_response", AsyncMock(return_value=workspace)),
            patch("app.services.auction_workspace.get_source_provider") as get_source_provider,
        ):
            response = await get_lot_workspace(session, source="tbankrot", lot_id="lot-1", refresh=False, include_detail=True)

        self.assertIs(response, workspace)
        get_cached_detail.assert_awaited_once_with(session, record)
        refresh_detail.assert_not_awaited()
        get_source_provider.assert_not_called()
        self.assertEqual(session.commits, 1)

    async def test_workspace_refresh_loads_price_schedule(self) -> None:
        record = AuctionLotRecord(
            id=1,
            source_code="tbankrot",
            auction_external_id=None,
            lot_external_id="lot-1",
            content_hash="hash",
            rating_score=88,
            rating_level="high",
            datagrid_row={},
            normalized_item={},
        )
        response = LotDetailResponse(
            source="tbankrot",
            url="https://example.test/lot-1",
            auction=AuctionSummary(source="tbankrot", external_id="auction-1", url="https://example.test/auction-1"),
            lot=LotSummary(source="tbankrot", external_id="lot-1", name="Экскаватор", price_schedule=[]),
            organizer=None,
            debtor=None,
            documents=[],
            raw_fields=[],
            raw_tables=[],
        )
        provider = StaticDetailProvider(response)
        session = FakeSession()

        with (
            patch("app.services.auction_workspace.find_lot_record", AsyncMock(return_value=record)),
            patch("app.services.auction_workspace.get_source_provider", return_value=provider),
            patch("app.services.auction_workspace.ensure_work_item", AsyncMock(return_value=SimpleNamespace(lot_record_id=1))),
            patch("app.services.auction_workspace.recalculate_record_rating"),
            patch("app.services.auction_workspace.generate_and_persist_lot_decision_report_snapshot", AsyncMock()),
            patch("app.services.auction_workspace.bump_auction_lot_dataset_version", AsyncMock()),
            patch("app.services.auction_workspace.auction_analysis_config_service.get_runtime_config", AsyncMock(return_value=_runtime_config())),
            patch("app.services.auction_workspace.build_workspace_response", AsyncMock(return_value=SimpleNamespace(marker="workspace"))),
        ):
            await get_lot_workspace(session, source="tbankrot", lot_id="lot-1", refresh=True, include_detail=True)

        self.assertEqual(provider.include_price_schedule_calls, [True])

    async def test_live_workspace_refresh_loads_price_schedule(self) -> None:
        record = AuctionLotRecord(
            id=1,
            source_code="tbankrot",
            auction_external_id=None,
            lot_external_id="lot-1",
            content_hash="hash",
            rating_score=88,
            rating_level="high",
            datagrid_row={},
            normalized_item={},
        )
        response = LotDetailResponse(
            source="tbankrot",
            url="https://example.test/lot-1",
            auction=AuctionSummary(source="tbankrot", external_id="auction-1", url="https://example.test/auction-1"),
            lot=LotSummary(source="tbankrot", external_id="lot-1", name="Экскаватор", price_schedule=[]),
            organizer=None,
            debtor=None,
            documents=[],
            raw_fields=[],
            raw_tables=[],
        )
        provider = StaticDetailProvider(response)
        session = FakeSession()

        with (
            patch("app.services.auction_workspace.find_lot_record", AsyncMock(return_value=record)),
            patch("app.services.auction_workspace.get_source_provider", return_value=provider),
            patch("app.services.auction_workspace.ensure_work_item", AsyncMock(return_value=SimpleNamespace(lot_record_id=1))),
            patch("app.services.auction_workspace.recalculate_record_rating"),
            patch("app.services.auction_workspace.generate_and_persist_lot_decision_report_snapshot", AsyncMock()),
            patch("app.services.auction_workspace.bump_auction_lot_dataset_version", AsyncMock()),
            patch("app.services.auction_workspace.publish_auction_event", AsyncMock()),
            patch("app.services.auction_workspace.auction_analysis_config_service.get_runtime_config", AsyncMock(return_value=_runtime_config())),
            patch(
                "app.services.auction_workspace.build_workspace_response",
                AsyncMock(
                    return_value=SimpleNamespace(
                        marker="workspace",
                        record_id=1,
                        detail_cached_at=None,
                        row=SimpleNamespace(model_dump=lambda mode: {}),
                    )
                ),
            ),
        ):
            await refresh_lot_workspace_live(session, source="tbankrot", lot_id="lot-1")

        self.assertEqual(provider.include_price_schedule_calls, [True])

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

    async def test_detail_refresh_invalidates_score_when_content_hash_changes(self) -> None:
        response = LotDetailResponse(
            source="tbankrot",
            url="https://example.test/lot-1",
            auction=AuctionSummary(source="tbankrot", external_id="auction-1", url="https://example.test/auction-1"),
            lot=LotSummary(
                source="tbankrot",
                external_id="lot-1",
                name="Экскаватор гусеничный",
                region="Московская область",
                city="Химки",
                status="Идет прием заявок",
            ),
            organizer=None,
            debtor=None,
            documents=[],
            raw_fields=[],
            raw_tables=[],
        )
        changed_response = LotDetailResponse(
            source="tbankrot",
            url="https://example.test/lot-1",
            auction=AuctionSummary(source="tbankrot", external_id="auction-1", url="https://example.test/auction-1"),
            lot=LotSummary(
                source="tbankrot",
                external_id="lot-1",
                name="Экскаватор гусеничный",
                region="Самарская область",
                city="Самара",
                status="Идет прием заявок",
            ),
            organizer=None,
            debtor=None,
            documents=[],
            raw_fields=[],
            raw_tables=[],
        )
        existing_cache = AuctionLotDetailCache(
            lot_record_id=1,
            content_hash=_lot_detail_content_hash(response),
            lot_detail=_lot_detail_payload_with_price_schedule_state(
                response.model_dump(mode="json"),
                previous_payload=None,
                include_price_schedule=False,
            ),
            auction_detail=None,
            documents=[],
        )
        record = AuctionLotRecord(
            id=1,
            source_code="tbankrot",
            auction_external_id=None,
            lot_external_id="lot-1",
            content_hash="record-hash",
            rating_score=88,
            rating_level="high",
            scoring_version="deterministic-v2",
            scored_at=datetime(2026, 5, 7, tzinfo=UTC),
            score_input_hash="score-hash",
            score_breakdown={"score": 88, "mode": "record"},
            datagrid_row={},
            normalized_item={},
        )

        with patch("app.services.auction_workspace.get_source_provider", return_value=StaticDetailProvider(changed_response)):
            with patch("app.services.auction_workspace.invalidate_lot_score", wraps=invalidate_lot_score) as invalidate_score:
                detail_cache = await ensure_lot_detail_cache(FakeSession(existing_cache), record, refresh=True, include_price_schedule=False)

        self.assertIs(detail_cache, existing_cache)
        invalidate_score.assert_called_once()
        self.assertIsNone(record.score_input_hash)
        self.assertEqual(record.rating_score, 88)
        self.assertEqual(record.rating_level, "high")
        self.assertEqual(record.score_breakdown, {"score": 88, "mode": "record"})

    async def test_detail_refresh_with_unchanged_content_preserves_score_identity(self) -> None:
        response = LotDetailResponse(
            source="tbankrot",
            url="https://example.test/lot-1",
            auction=AuctionSummary(source="tbankrot", external_id="auction-1", url="https://example.test/auction-1"),
            lot=LotSummary(
                source="tbankrot",
                external_id="lot-1",
                name="Экскаватор гусеничный",
                region="Московская область",
                city="Химки",
                status="Идет прием заявок",
            ),
            organizer=None,
            debtor=None,
            documents=[],
            raw_fields=[],
            raw_tables=[],
        )
        existing_cache = AuctionLotDetailCache(
            lot_record_id=1,
            content_hash=_lot_detail_content_hash(response),
            lot_detail=_lot_detail_payload_with_price_schedule_state(
                response.model_dump(mode="json"),
                previous_payload=None,
                include_price_schedule=False,
            ),
            auction_detail=None,
            documents=[],
        )
        record = AuctionLotRecord(
            id=1,
            source_code="tbankrot",
            auction_external_id=None,
            lot_external_id="lot-1",
            content_hash="record-hash",
            rating_score=88,
            rating_level="high",
            scoring_version="deterministic-v2",
            scored_at=datetime(2026, 5, 7, tzinfo=UTC),
            score_input_hash="score-hash",
            score_breakdown={"score": 88, "mode": "record"},
            datagrid_row={},
            normalized_item={},
        )

        with patch("app.services.auction_workspace.get_source_provider", return_value=StaticDetailProvider(response)):
            with patch("app.services.auction_workspace.invalidate_lot_score", wraps=invalidate_lot_score) as invalidate_score:
                await ensure_lot_detail_cache(FakeSession(existing_cache), record, refresh=True, include_price_schedule=False)

        invalidate_score.assert_not_called()
        self.assertEqual(record.score_input_hash, "score-hash")
        self.assertEqual(record.rating_score, 88)
        self.assertEqual(record.score_breakdown, {"score": 88, "mode": "record"})


if __name__ == "__main__":
    unittest.main()
