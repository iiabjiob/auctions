from __future__ import annotations

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.models.auction import AuctionLotDetailCache, AuctionLotRecord, AuctionSourceState, AuctionSourceSyncState
from app.schemas.auctions import AuctionListItem, AuctionSummary, LotImage, LotSummary, OrganizerInfo, PriceScheduleStep
from app.services.auction_scoring import invalidate_lot_score
from app.services.lot_enrichment import classify_lot_enrichment
from app.services.lot_enrichment import schedule_lot_enrichment
from app.services.lot_enrichment import schedule_lot_ttl_refresh
from app.services.auction_sync import (
    _backfill_publication_dates,
    _prepare_snapshot,
    _preserve_existing_real_media,
    _sync_detail_if_needed,
    sync_source_lots,
)


FIXED_SYNC_NOW = datetime(2026, 5, 7, 12, tzinfo=UTC)


class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return FIXED_SYNC_NOW
        return FIXED_SYNC_NOW.astimezone(tz)


def make_list_item(
    *,
    lot_name: str = "Экскаватор",
    status: str = "Идет прием заявок",
    category: str | None = "Спецтехника",
    location_region: str | None = "Московская область",
    application_deadline: str | None = "05.05.2026 18:00",
    initial_price: str | None = "1 000 000 руб.",
    images: list[LotImage] | None = None,
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
            images=images or [],
            primary_image_url=images[0].url if images else None,
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
        enrichment_requested_at=None,
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
        self.pages = []

    def info(self):
        return SimpleNamespace(code=self.code, title=self.title, website=self.website, enabled=True)

    def iter_lots(self, limit: int | None = None, *, page: int = 1):
        self.pages.append(page)
        return iter(self._items if limit is None else self._items[:limit])


class FakeSession:
    def __init__(self, *, source_state=None, source_sync_state=None):
        self.added = []
        self.commits = 0
        self.source_state = source_state
        self.source_sync_state = source_sync_state

    async def get(self, model, key):
        if self.source_state is not None and model is AuctionSourceState and key == self.source_state.code:
            return self.source_state
        if self.source_sync_state is not None and model is AuctionSourceSyncState and key == self.source_sync_state.source_code:
            return self.source_sync_state
        if model is AuctionSourceState and key == "tbankrot":
            return None
        if model is AuctionSourceSyncState and key == "tbankrot":
            return None
        return None

    def add(self, item) -> None:
        self.added.append(item)

    async def scalar(self, statement):
        return None

    async def flush(self):
        return None

    async def commit(self):
        self.commits += 1


class FakeScalarResult:
    def __init__(self, items):
        self._items = items

    def all(self):
        return list(self._items)


class BackfillFakeSession:
    def __init__(self, *, records=None, detail_caches=None, affected_records=None):
        self._results = [
            records or [],
            detail_caches or [],
            affected_records or [],
        ]
        self.statements = []

    async def scalars(self, statement):
        self.statements.append(statement)
        items = self._results.pop(0) if self._results else []
        return FakeScalarResult(items)


class AuctionSyncInvalidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_record_populates_search_text_during_sync(self) -> None:
        item = make_list_item(lot_name="  BMW   X5  ", category="Авто", location_region="Москва")
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
            patch("app.services.auction_sync._find_lot_record", AsyncMock(return_value=None)),
            patch("app.services.auction_sync._recalculate_record_with_cached_inputs", AsyncMock()),
            patch("app.services.auction_sync._sync_detail_if_needed", AsyncMock(return_value=0)),
            patch("app.services.auction_sync._backfill_publication_dates", AsyncMock()),
            patch("app.services.auction_sync.bump_auction_lot_dataset_version", AsyncMock()),
            patch("app.services.auction_sync.auction_analysis_config_service.get_runtime_config", AsyncMock(return_value=runtime_config)),
            patch("app.services.auction_sync.classify_lot_enrichment", return_value=SimpleNamespace(needs_enrichment=False)),
        ):
            await sync_source_lots(session, source="tbankrot", limit=1)

        record = next(item for item in session.added if isinstance(item, AuctionLotRecord))
        self.assertEqual(record.search_text, "bmw x5 tbankrot авто organizer")

    async def test_tbankrot_page_rotation_uses_source_cursor_and_advances_window(self) -> None:
        item = make_list_item()
        source_state = AuctionSourceState(
            code="tbankrot",
            title="TBankrot",
            website="https://tbankrot.ru",
            enabled=True,
        )
        source_sync_state = AuctionSourceSyncState(
            source_code="tbankrot",
            next_page=6,
        )
        session = FakeSession(source_state=source_state, source_sync_state=source_sync_state)
        runtime_config = SimpleNamespace(
            category_keywords={},
            exclusion_keywords=(),
            legal_risk_rules=SimpleNamespace(),
            owner_profile=SimpleNamespace(),
            dimension_weights=SimpleNamespace(),
        )
        provider = StaticSourceProvider([item])

        with (
            patch("app.services.auction_sync.settings.tbankrot_page_rotation_enabled", True),
            patch("app.services.auction_sync.settings.tbankrot_pages", 5),
            patch("app.services.auction_sync.settings.tbankrot_page_rotation_max_page", 20),
            patch("app.services.auction_sync.get_source_provider", return_value=provider),
            patch("app.services.auction_sync._find_lot_record", AsyncMock(return_value=None)),
            patch("app.services.auction_sync._recalculate_record_with_cached_inputs", AsyncMock()),
            patch("app.services.auction_sync._sync_detail_if_needed", AsyncMock(return_value=0)),
            patch("app.services.auction_sync._backfill_publication_dates", AsyncMock()),
            patch("app.services.auction_sync.bump_auction_lot_dataset_version", AsyncMock()),
            patch("app.services.auction_sync.auction_analysis_config_service.get_runtime_config", AsyncMock(return_value=runtime_config)),
            patch("app.services.auction_sync.classify_lot_enrichment", return_value=SimpleNamespace(needs_enrichment=False)),
        ):
            await sync_source_lots(session, source="tbankrot", limit=1)

        self.assertEqual(provider.pages, [6])
        self.assertEqual(source_sync_state.next_page, 11)
        self.assertEqual(source_sync_state.last_start_page, 6)
        self.assertEqual(source_sync_state.last_window_size, 5)
        self.assertEqual(source_sync_state.last_fetched, 1)

    async def test_tbankrot_page_rotation_wraps_after_max_page(self) -> None:
        item = make_list_item()
        source_state = AuctionSourceState(
            code="tbankrot",
            title="TBankrot",
            website="https://tbankrot.ru",
            enabled=True,
        )
        source_sync_state = AuctionSourceSyncState(
            source_code="tbankrot",
            next_page=18,
        )
        session = FakeSession(source_state=source_state, source_sync_state=source_sync_state)
        runtime_config = SimpleNamespace(
            category_keywords={},
            exclusion_keywords=(),
            legal_risk_rules=SimpleNamespace(),
            owner_profile=SimpleNamespace(),
            dimension_weights=SimpleNamespace(),
        )
        provider = StaticSourceProvider([item])

        with (
            patch("app.services.auction_sync.settings.tbankrot_page_rotation_enabled", True),
            patch("app.services.auction_sync.settings.tbankrot_pages", 5),
            patch("app.services.auction_sync.settings.tbankrot_page_rotation_max_page", 20),
            patch("app.services.auction_sync.get_source_provider", return_value=provider),
            patch("app.services.auction_sync._find_lot_record", AsyncMock(return_value=None)),
            patch("app.services.auction_sync._recalculate_record_with_cached_inputs", AsyncMock()),
            patch("app.services.auction_sync._sync_detail_if_needed", AsyncMock(return_value=0)),
            patch("app.services.auction_sync._backfill_publication_dates", AsyncMock()),
            patch("app.services.auction_sync.bump_auction_lot_dataset_version", AsyncMock()),
            patch("app.services.auction_sync.auction_analysis_config_service.get_runtime_config", AsyncMock(return_value=runtime_config)),
            patch("app.services.auction_sync.classify_lot_enrichment", return_value=SimpleNamespace(needs_enrichment=False)),
        ):
            await sync_source_lots(session, source="tbankrot", limit=1)

        self.assertEqual(provider.pages, [18])
        self.assertEqual(source_sync_state.next_page, 1)
        self.assertEqual(source_sync_state.last_start_page, 18)
        self.assertEqual(source_sync_state.last_window_size, 5)

    def test_preserve_existing_real_media_when_next_sync_has_only_locked_placeholders(self) -> None:
        existing_item = make_list_item(
            images=[
                LotImage(
                    url="https://tbankrot.ru/upload/lot/photo.jpg",
                    thumbnail_url="https://tbankrot.ru/upload/lot/photo-thumb.jpg",
                    source="tbankrot",
                )
            ]
        )
        next_item = make_list_item(
            images=[
                LotImage(
                    url="https://tbankrot.ru/img/blur/photo.jpg",
                    thumbnail_url="https://tbankrot.ru/img/blur/photo.jpg",
                    source="tbankrot",
                )
            ]
        )
        existing_snapshot = _prepare_snapshot(existing_item, "TBankrot")
        next_snapshot = _prepare_snapshot(next_item, "TBankrot")
        record = make_record(existing_snapshot, content_hash=existing_snapshot.content_hash)

        _preserve_existing_real_media(record, next_snapshot)

        self.assertEqual(next_snapshot.datagrid_row["primary_image_url"], "https://tbankrot.ru/upload/lot/photo.jpg")
        self.assertEqual(next_snapshot.datagrid_row["images"][0]["url"], "https://tbankrot.ru/upload/lot/photo.jpg")
        self.assertEqual(next_snapshot.normalized_item["lot"]["images"][0]["url"], "https://tbankrot.ru/upload/lot/photo.jpg")

    def test_price_schedule_does_not_affect_list_content_hash(self) -> None:
        without_schedule = make_list_item()
        with_schedule = make_list_item()
        with_schedule.lot.price_schedule = [PriceScheduleStep(starts_at="01.05.2026", price="900 000 руб.")]

        first_snapshot = _prepare_snapshot(without_schedule, "TBankrot")
        second_snapshot = _prepare_snapshot(with_schedule, "TBankrot")

        self.assertEqual(first_snapshot.content_hash, second_snapshot.content_hash)
        self.assertEqual(second_snapshot.normalized_item["lot"]["price_schedule"][0]["price"], "900 000 руб.")

    async def test_source_content_change_schedules_enrichment_when_evidence_is_missing(self) -> None:
        item = make_list_item(initial_price=None)
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
            patch("app.services.auction_sync.classify_lot_enrichment", return_value=SimpleNamespace(needs_enrichment=True)) as classify_enrichment,
            patch("app.services.auction_sync.schedule_lot_enrichment", wraps=schedule_lot_enrichment) as schedule_enrichment,
            patch("app.services.auction_sync.invalidate_lot_score", wraps=invalidate_lot_score),
        ):
            await sync_source_lots(session, source="tbankrot", limit=1)

        classify_enrichment.assert_called_once()
        schedule_enrichment.assert_called_once()
        self.assertIsNotNone(record.enrichment_requested_at)

    async def test_publication_backfill_is_disabled_when_limit_is_zero(self) -> None:
        session = BackfillFakeSession(records=[make_record(_prepare_snapshot(make_list_item(), "TBankrot"), content_hash="hash")])

        with patch("app.services.auction_sync.settings.auction_publication_sync_limit", 0):
            await _backfill_publication_dates(
                session,
                source_code="tbankrot",
                observed_at=datetime(2026, 5, 7, tzinfo=UTC),
            )

        self.assertEqual(session.statements, [])

    async def test_publication_backfill_limits_record_scan_and_detail_cache_load(self) -> None:
        records = []
        for index in range(3):
            item = make_list_item()
            item.auction.external_id = f"auction-{index}"
            item.lot.external_id = f"lot-{index}"
            snapshot = _prepare_snapshot(item, "TBankrot")
            record = make_record(snapshot, content_hash=snapshot.content_hash)
            record.id = index + 1
            record.auction_external_id = item.auction.external_id
            record.lot_external_id = item.lot.external_id
            record.datagrid_row = {"freshness": {}}
            record.normalized_item = {"auction": {}, "lot": {}}
            records.append(record)

        session = BackfillFakeSession(records=records, detail_caches=[])
        provider = SimpleNamespace(get_auction_publication_date=lambda auction_id: None)

        with (
            patch("app.services.auction_sync.settings.auction_publication_sync_limit", 2),
            patch("app.services.auction_sync.get_source_provider", return_value=provider),
        ):
            await _backfill_publication_dates(
                session,
                source_code="tbankrot",
                observed_at=datetime(2026, 5, 7, tzinfo=UTC),
            )

        self.assertEqual(len(session.statements), 2)
        self.assertEqual(getattr(session.statements[0]._limit_clause, "value", None), 2)
        detail_cache_statement = session.statements[1]
        self.assertIn("auction_lot_detail_caches", str(detail_cache_statement))

    async def test_source_content_change_does_not_schedule_enrichment_when_local_evidence_is_sufficient(self) -> None:
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
            patch("app.services.auction_sync.classify_lot_enrichment", return_value=SimpleNamespace(needs_enrichment=False)) as classify_enrichment,
            patch("app.services.auction_sync.schedule_lot_enrichment", wraps=schedule_lot_enrichment) as schedule_enrichment,
            patch("app.services.auction_sync.invalidate_lot_score", wraps=invalidate_lot_score),
        ):
            await sync_source_lots(session, source="tbankrot", limit=1)

        classify_enrichment.assert_called_once()
        schedule_enrichment.assert_not_called()
        self.assertIsNone(record.enrichment_requested_at)

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

    async def test_repeated_identical_sync_does_not_duplicate_enrichment_scheduling(self) -> None:
        item = make_list_item(initial_price=None)
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
            patch("app.services.auction_sync.classify_lot_enrichment", return_value=SimpleNamespace(needs_enrichment=True)) as classify_enrichment,
            patch("app.services.auction_sync.schedule_lot_enrichment", wraps=schedule_lot_enrichment) as schedule_enrichment,
            patch("app.services.auction_sync.invalidate_lot_score", wraps=invalidate_lot_score),
        ):
            await sync_source_lots(session, source="tbankrot", limit=1)
            first_requested_at = record.enrichment_requested_at
            await sync_source_lots(session, source="tbankrot", limit=1)

        self.assertEqual(classify_enrichment.call_count, 1)
        self.assertEqual(schedule_enrichment.call_count, 1)
        self.assertEqual(record.enrichment_requested_at, first_requested_at)

    async def test_sync_sets_actuality_columns_for_active_records(self) -> None:
        item = make_list_item(application_deadline="10.05.2026 18:00")
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
            patch("app.services.auction_sync.datetime", FixedDateTime),
            patch("app.services.auction_sync.get_source_provider", return_value=provider),
            patch("app.services.auction_sync._find_lot_record", AsyncMock(return_value=None)),
            patch("app.services.auction_sync._recalculate_record_with_cached_inputs", AsyncMock()),
            patch("app.services.auction_sync._sync_detail_if_needed", AsyncMock(return_value=0)),
            patch("app.services.auction_sync._backfill_publication_dates", AsyncMock()),
            patch("app.services.auction_sync.bump_auction_lot_dataset_version", AsyncMock()),
            patch("app.services.auction_sync.auction_analysis_config_service.get_runtime_config", AsyncMock(return_value=runtime_config)),
            patch("app.services.auction_sync.classify_lot_enrichment", return_value=SimpleNamespace(needs_enrichment=False)),
        ):
            await sync_source_lots(session, source="tbankrot", limit=1)

        record = next(item for item in session.added if isinstance(item, AuctionLotRecord))
        self.assertEqual(record.lifecycle_status, "active")
        self.assertEqual(record.publication_at, datetime(2026, 5, 1, tzinfo=UTC))
        self.assertEqual(record.application_deadline_at, datetime(2026, 5, 10, 18, tzinfo=UTC))
        self.assertIsNone(record.archived_at)
        self.assertIsNone(record.archive_reason)
        self.assertEqual(record.actuality_checked_at, FIXED_SYNC_NOW)
        self.assertIsNone(record.enrichment_requested_at)

    async def test_sync_marks_expired_records_and_clears_enrichment_state(self) -> None:
        item = make_list_item(application_deadline="05.05.2026 18:00")
        snapshot = _prepare_snapshot(item, "TBankrot")
        record = make_record(snapshot, content_hash="old-content-hash")
        record.enrichment_requested_at = datetime(2026, 5, 6, tzinfo=UTC)
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
            patch("app.services.auction_sync.datetime", FixedDateTime),
            patch("app.services.auction_sync.get_source_provider", return_value=provider),
            patch("app.services.auction_sync._find_lot_record", AsyncMock(return_value=record)),
            patch("app.services.auction_sync._recalculate_record_with_cached_inputs", AsyncMock()),
            patch("app.services.auction_sync._sync_detail_if_needed", AsyncMock(return_value=0)),
            patch("app.services.auction_sync._backfill_publication_dates", AsyncMock()),
            patch("app.services.auction_sync.bump_auction_lot_dataset_version", AsyncMock()),
            patch("app.services.auction_sync.auction_analysis_config_service.get_runtime_config", AsyncMock(return_value=runtime_config)),
            patch("app.services.auction_sync.classify_lot_enrichment", return_value=SimpleNamespace(needs_enrichment=True)),
            patch("app.services.auction_sync.schedule_lot_enrichment", wraps=schedule_lot_enrichment) as schedule_enrichment,
        ):
            await sync_source_lots(session, source="tbankrot", limit=1)

        schedule_enrichment.assert_not_called()
        self.assertEqual(record.lifecycle_status, "expired")
        self.assertEqual(record.finished_at, datetime(2026, 5, 5, 18, tzinfo=UTC))
        self.assertEqual(record.archived_at, FIXED_SYNC_NOW)
        self.assertEqual(record.archive_reason, "application_deadline_passed")
        self.assertEqual(record.actuality_checked_at, FIXED_SYNC_NOW)
        self.assertIsNone(record.enrichment_requested_at)

    async def test_sync_restores_active_records_after_terminal_status(self) -> None:
        item = make_list_item(application_deadline="10.05.2026 18:00")
        snapshot = _prepare_snapshot(item, "TBankrot")
        record = make_record(snapshot, content_hash="old-content-hash", score_input_hash="score-hash")
        record.status = "Торги состоялись"
        record.lifecycle_status = "archived"
        record.archived_at = datetime(2026, 5, 6, tzinfo=UTC)
        record.archive_reason = "terminal_status"
        record.finished_at = datetime(2026, 5, 6, tzinfo=UTC)
        record.enrichment_requested_at = datetime(2026, 5, 6, tzinfo=UTC)
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
            patch("app.services.auction_sync.datetime", FixedDateTime),
            patch("app.services.auction_sync.get_source_provider", return_value=provider),
            patch("app.services.auction_sync._find_lot_record", AsyncMock(return_value=record)),
            patch("app.services.auction_sync._recalculate_record_with_cached_inputs", AsyncMock()),
            patch("app.services.auction_sync._sync_detail_if_needed", AsyncMock(return_value=0)),
            patch("app.services.auction_sync._backfill_publication_dates", AsyncMock()),
            patch("app.services.auction_sync.bump_auction_lot_dataset_version", AsyncMock()),
            patch("app.services.auction_sync.auction_analysis_config_service.get_runtime_config", AsyncMock(return_value=runtime_config)),
            patch("app.services.auction_sync.classify_lot_enrichment", return_value=SimpleNamespace(needs_enrichment=False)),
        ):
            await sync_source_lots(session, source="tbankrot", limit=1)

        self.assertEqual(record.lifecycle_status, "active")
        self.assertIsNone(record.archived_at)
        self.assertIsNone(record.archive_reason)
        self.assertIsNone(record.finished_at)
        self.assertEqual(record.actuality_checked_at, FIXED_SYNC_NOW)
        self.assertIsNone(record.enrichment_requested_at)

    async def test_stale_high_value_detail_cache_schedules_ttl_refresh_via_detail_sync(self) -> None:
        item = make_list_item()
        snapshot = _prepare_snapshot(item, "TBankrot")
        record = make_record(snapshot, content_hash=snapshot.content_hash)
        record.rating_score = 90
        detail_cache = AuctionLotDetailCache(
            lot_record_id=record.id,
            fetched_at=datetime(2026, 4, 29, tzinfo=UTC),
            content_hash="detail-hash",
            lot_detail={"lot": {}},
            auction_detail={"auction": {}},
            documents=[],
        )
        runtime_config = SimpleNamespace(
            category_keywords={},
            exclusion_keywords=(),
            legal_risk_rules=SimpleNamespace(),
            owner_profile=SimpleNamespace(),
            dimension_weights=SimpleNamespace(),
        )

        with (
            patch("app.services.auction_sync.settings.auction_detail_sync_enabled", True),
            patch("app.services.auction_sync.settings.auction_detail_sync_limit", 10),
            patch("app.services.auction_sync.ensure_lot_detail_cache", AsyncMock(return_value=detail_cache)),
            patch("app.services.auction_sync.ensure_work_item", AsyncMock(return_value=SimpleNamespace())),
            patch("app.services.auction_sync.recalculate_record_rating"),
            patch("app.services.auction_sync.schedule_lot_ttl_refresh", wraps=schedule_lot_ttl_refresh) as schedule_ttl,
        ):
            await _sync_detail_if_needed(
                AsyncMock(),
                record,
                detail_sync_count=0,
                refresh=False,
                observed_at=datetime(2026, 5, 7, tzinfo=UTC),
                runtime_config=runtime_config,
            )

        schedule_ttl.assert_called_once()
        self.assertIsNotNone(record.enrichment_requested_at)



if __name__ == "__main__":
    unittest.main()
