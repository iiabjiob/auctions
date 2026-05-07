from __future__ import annotations

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.models.auction import AuctionLotRecord, AuctionSourceState
from app.schemas.auctions import AuctionListItem, AuctionSummary, LotSummary, OrganizerInfo
from app.services.auction_scoring import invalidate_lot_score
from app.services.lot_enrichment import classify_lot_enrichment
from app.services.auction_sync import _prepare_snapshot, sync_source_lots


def make_list_item(
    *,
    lot_name: str = "Экскаватор",
    status: str = "Идет прием заявок",
    category: str | None = "Спецтехника",
    location_region: str | None = "Московская область",
    application_deadline: str | None = "05.05.2026 18:00",
    initial_price: str | None = "1 000 000 руб.",
) -> AuctionListItem:
    return AuctionListItem(
        source="tbankrot",
        auction=AuctionSummary(
            source="tbankrot",
            external_id="auction-1",
            number="A-1",
            name="Auction 1",
            publication_date="01.05.2026",
        ),
        lot=LotSummary(
            source="tbankrot",
            external_id="lot-1",
            number="1",
            name=lot_name,
            status=status,
            category=category,
            location_region=location_region,
            application_deadline=application_deadline,
            initial_price=initial_price,
        ),
        organizer=OrganizerInfo(name="Organizer"),
    )


def make_record(snapshot, *, content_hash: str, score_input_hash: str = "score-hash") -> AuctionLotRecord:
    return AuctionLotRecord(
        id=1,
        source_code="tbankrot",
        auction_external_id="auction-1",
        lot_external_id="lot-1",
        auction_number="A-1",
        lot_number="1",
        lot_name="Экскаватор",
        status="Идет прием заявок",
        initial_price="1 000 000 руб.",
        content_hash=content_hash,
        rating_score=88,
        rating_level="high",
        scoring_version="deterministic-v2",
        scored_at=datetime(2026, 5, 7, tzinfo=UTC),
        score_input_hash=score_input_hash,
        score_breakdown={"score": 88, "mode": "record"},
        datagrid_row=snapshot.datagrid_row,
        normalized_item=snapshot.normalized_item,
        first_seen_at=datetime(2026, 5, 7, tzinfo=UTC),
        last_seen_at=datetime(2026, 5, 7, tzinfo=UTC),
    )


class StaticSourceProvider:
    code = "tbankrot"
    title = "TBankrot"
    website = "https://tbankrot.ru"

    def __init__(self, items: list[AuctionListItem]):
        self._items = items

    def info(self):
        return SimpleNamespace(code=self.code, title=self.title, website=self.website, enabled=True)

    def iter_lots(self, limit: int | None = None):
        return iter(self._items if limit is None else self._items[:limit])


class FakeSession:
    def __init__(self):
        self.added = []
        self.commits = 0

    async def get(self, model, key):
        if model is AuctionSourceState and key == "tbankrot":
            return None
        return None

    def add(self, item) -> None:
        self.added.append(item)

    async def flush(self):
        return None

    async def commit(self):
        self.commits += 1


class AuctionSyncInvalidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_source_content_change_invalidates_score_identity_and_preserves_ui_score_state(self) -> None:
        item = make_list_item()
        snapshot = _prepare_snapshot(item, "TBankrot")
        record = make_record(snapshot, content_hash="old-content-hash")
        session = FakeSession()
        runtime_config = SimpleNamespace(
            category_keywords={},
            exclusion_keywords=(),
            legal_risk_rules=SimpleNamespace(),
            owner_profile=SimpleNamespace(),
            dimension_weights=SimpleNamespace(),
        )
        provider = StaticSourceProvider([item])

        with (
            patch("app.services.auction_sync.get_source_provider", return_value=provider),
            patch("app.services.auction_sync._find_lot_record", AsyncMock(return_value=record)),
            patch("app.services.auction_sync._recalculate_record_with_cached_inputs", AsyncMock()),
            patch("app.services.auction_sync._sync_detail_if_needed", AsyncMock(return_value=0)),
            patch("app.services.auction_sync._backfill_publication_dates", AsyncMock()),
            patch("app.services.auction_sync.bump_auction_lot_dataset_version", AsyncMock()),
            patch("app.services.auction_sync.auction_analysis_config_service.get_runtime_config", AsyncMock(return_value=runtime_config)),
            patch("app.services.auction_sync.classify_lot_enrichment", wraps=classify_lot_enrichment) as classify_enrichment,
            patch("app.services.auction_sync.invalidate_lot_score", wraps=invalidate_lot_score) as invalidate_score,
        ):
            await sync_source_lots(session, source="tbankrot", limit=1)

        classify_enrichment.assert_called_once()
        invalidate_score.assert_called_once()
        self.assertIsNone(record.score_input_hash)
        self.assertEqual(record.rating_score, 88)
        self.assertEqual(record.rating_level, "high")
        self.assertEqual(record.score_breakdown, {"score": 88, "mode": "record"})

    async def test_unchanged_source_content_does_not_invalidate_score_identity(self) -> None:
        item = make_list_item()
        snapshot = _prepare_snapshot(item, "TBankrot")
        record = make_record(snapshot, content_hash=snapshot.content_hash)
        session = FakeSession()
        runtime_config = SimpleNamespace(
            category_keywords={},
            exclusion_keywords=(),
            legal_risk_rules=SimpleNamespace(),
            owner_profile=SimpleNamespace(),
            dimension_weights=SimpleNamespace(),
        )
        provider = StaticSourceProvider([item])

        with (
            patch("app.services.auction_sync.get_source_provider", return_value=provider),
            patch("app.services.auction_sync._find_lot_record", AsyncMock(return_value=record)),
            patch("app.services.auction_sync._recalculate_record_with_cached_inputs", AsyncMock()),
            patch("app.services.auction_sync._sync_detail_if_needed", AsyncMock(return_value=0)),
            patch("app.services.auction_sync._backfill_publication_dates", AsyncMock()),
            patch("app.services.auction_sync.bump_auction_lot_dataset_version", AsyncMock()),
            patch("app.services.auction_sync.auction_analysis_config_service.get_runtime_config", AsyncMock(return_value=runtime_config)),
            patch("app.services.auction_sync.classify_lot_enrichment", wraps=classify_lot_enrichment) as classify_enrichment,
            patch("app.services.auction_sync.invalidate_lot_score", wraps=invalidate_lot_score) as invalidate_score,
        ):
            await sync_source_lots(session, source="tbankrot", limit=1)

        classify_enrichment.assert_not_called()
        invalidate_score.assert_not_called()
        self.assertIsNotNone(record.score_input_hash)
        self.assertGreater(record.rating_score, 0)
        self.assertIn("mode", record.score_breakdown)


if __name__ == "__main__":
    unittest.main()
