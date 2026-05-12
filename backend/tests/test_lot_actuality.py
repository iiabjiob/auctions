from __future__ import annotations

import asyncio
import unittest
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.models.auction import AuctionLotDetailCache, AuctionLotRecord
from app.schemas.auctions import LotDatagridRow, LotFreshness, LotRating
from app.services.lot_actuality import (
    classify_lot_actuality,
    extract_lot_actuality_dates,
    parse_lot_datetime,
    _list_actuality_sweep_candidates,
    run_lot_actuality_sweep,
)


def make_record(
    *,
    status: str = "Идет прием заявок",
    last_seen_at: datetime | None = None,
    application_deadline: str | None = "05.05.2026 18:00",
    auction_date: str | None = "07.05.2026 10:00",
) -> AuctionLotRecord:
    row = LotDatagridRow(
        row_id="tbankrot:auction-1:lot-1",
        source="tbankrot",
        source_title="TBankrot",
        auction_id="auction-1",
        auction_number="A-1",
        auction_name="Торги",
        lot_id="lot-1",
        lot_number="1",
        lot_name="Экскаватор гусеничный",
        lot_description="Подробное описание",
        category="Спецтехника",
        location="Московская область, Химки",
        location_region="Московская область",
        location_city="Химки",
        location_address="ул. Ленина, 1",
        location_coordinates="55.89, 37.45",
        model_category="Спецтехника",
        status=status,
        initial_price="1 000 000 руб.",
        initial_price_value=Decimal("1000000"),
        current_price="900 000 руб.",
        current_price_value=Decimal("900000"),
        minimum_price="800 000 руб.",
        minimum_price_value=Decimal("800000"),
        price_schedule=[],
        images=[],
        primary_image_url=None,
        image_count=0,
        publication_date="01.05.2026",
        application_deadline=application_deadline,
        auction_date=auction_date,
        market_value=Decimal("2000000"),
        exclude_from_analysis=False,
        freshness=LotFreshness(is_new=True),
        rating=LotRating(score=0, level="low", reasons=[]),
    )
    record = AuctionLotRecord(
        id=1,
        source_code="tbankrot",
        auction_external_id="auction-1",
        lot_external_id="lot-1",
        auction_number="A-1",
        lot_number="1",
        lot_name="Экскаватор гусеничный",
        status=status,
        initial_price="1 000 000 руб.",
        content_hash="content-hash",
        is_new=True,
        datagrid_row=row.model_dump(mode="json"),
        normalized_item={
            "auction": {
                "publication_date": "01.05.2026",
                "application_deadline": application_deadline,
                "auction_date": auction_date,
            },
            "lot": {
                "category": "Спецтехника",
                "region": "Московская область",
                "city": "Химки",
                "address": "ул. Ленина, 1",
                "coordinates": "55.89, 37.45",
            },
        },
    )
    record.lifecycle_status = "active"
    if last_seen_at is not None:
        record.last_seen_at = last_seen_at
    return record


def make_detail_cache() -> AuctionLotDetailCache:
    return AuctionLotDetailCache(
        lot_record_id=1,
        content_hash="detail-hash",
        lot_detail={
            "lot": {
                "description": "Подробное описание",
                "inspection_order": "По записи",
            },
            "raw_fields": [
                {"name": "Прием заявок", "value": "с 02.05.2026 09:00 до 05.05.2026 18:00"},
                {"name": "Проведение торгов", "value": "07.05.2026 10:00"},
            ],
        },
        auction_detail={"auction": {"publication_date": "01.05.2026"}},
        documents=[],
    )


class FakeScalarResult:
    def __init__(self, items: list[object]) -> None:
        self._items = items

    def all(self) -> list[object]:
        return list(self._items)


class FakeSweepSession:
    def __init__(self, *, scalar_batches: list[list[object]] | None = None) -> None:
        self.scalar_batches = list(scalar_batches or [])
        self.scalars_calls: list[object] = []

    async def scalars(self, statement):  # noqa: ANN001
        self.scalars_calls.append(statement)
        return FakeScalarResult(self.scalar_batches.pop(0) if self.scalar_batches else [])


class LotActualityTests(unittest.TestCase):
    def test_parse_lot_datetime_supports_common_scraped_formats(self) -> None:
        self.assertEqual(parse_lot_datetime("05.05.2026 18:00"), datetime(2026, 5, 5, 18, 0, tzinfo=UTC))
        self.assertEqual(parse_lot_datetime("05.05.2026"), datetime(2026, 5, 5, 0, 0, tzinfo=UTC))
        self.assertEqual(parse_lot_datetime("2026-05-05T18:00:00+03:00"), datetime(2026, 5, 5, 15, 0, tzinfo=UTC))
        self.assertIsNone(parse_lot_datetime(None))

    def test_extract_lot_actuality_dates_merges_row_normalized_item_and_detail_cache(self) -> None:
        record = make_record(
            application_deadline="05.05.2026 18:00",
            auction_date="07.05.2026 10:00",
        )
        detail_cache = make_detail_cache()

        dates = extract_lot_actuality_dates(record, detail_cache)

        self.assertEqual(dates.publication_at, datetime(2026, 5, 1, 0, 0, tzinfo=UTC))
        self.assertEqual(dates.application_start_at, datetime(2026, 5, 2, 9, 0, tzinfo=UTC))
        self.assertEqual(dates.application_deadline_at, datetime(2026, 5, 5, 18, 0, tzinfo=UTC))
        self.assertEqual(dates.auction_at, datetime(2026, 5, 7, 10, 0, tzinfo=UTC))

    def test_classify_lot_actuality_marks_active_when_dates_are_future_and_recent(self) -> None:
        current_time = datetime(2026, 5, 7, 12, tzinfo=UTC)
        record = make_record(
            last_seen_at=current_time - timedelta(days=1),
            application_deadline="08.05.2026 18:00",
            auction_date="10.05.2026 10:00",
        )

        classification = classify_lot_actuality(record, current_time=current_time)

        self.assertEqual(classification.lifecycle_status, "active")
        self.assertIsNone(classification.finished_at)
        self.assertIsNone(classification.archive_reason)

    def test_classify_lot_actuality_marks_expired_when_deadline_passed(self) -> None:
        current_time = datetime(2026, 5, 7, 12, tzinfo=UTC)
        record = make_record(
            application_deadline="05.05.2026 18:00",
            auction_date="10.05.2026 10:00",
            last_seen_at=current_time - timedelta(days=1),
        )

        classification = classify_lot_actuality(record, current_time=current_time)

        self.assertEqual(classification.lifecycle_status, "expired")
        self.assertEqual(classification.finished_at, datetime(2026, 5, 5, 18, 0, tzinfo=UTC))
        self.assertEqual(classification.archive_reason, "application_deadline_passed")

    def test_classify_lot_actuality_marks_archived_for_terminal_status(self) -> None:
        current_time = datetime(2026, 5, 7, 12, tzinfo=UTC)
        record = make_record(
            status="Торги состоялись",
            application_deadline="10.05.2026 18:00",
            auction_date="12.05.2026 10:00",
            last_seen_at=current_time - timedelta(days=1),
        )

        classification = classify_lot_actuality(record, current_time=current_time)

        self.assertEqual(classification.lifecycle_status, "archived")
        self.assertEqual(classification.finished_at, current_time)
        self.assertEqual(classification.archive_reason, "terminal_status")

    def test_classify_lot_actuality_marks_stale_when_last_seen_is_old(self) -> None:
        current_time = datetime(2026, 5, 7, 12, tzinfo=UTC)
        record = make_record(
            last_seen_at=current_time - timedelta(days=31),
            application_deadline="10.05.2026 18:00",
            auction_date="12.05.2026 10:00",
        )

        classification = classify_lot_actuality(record, current_time=current_time)

        self.assertEqual(classification.lifecycle_status, "stale")
        self.assertEqual(classification.finished_at, datetime(2026, 5, 7, 12, tzinfo=UTC) - timedelta(days=1))
        self.assertEqual(classification.archive_reason, "last_seen_too_old")

    def test_run_lot_actuality_sweep_marks_expired_records_and_bumps_row_deleted(self) -> None:
        current_time = datetime(2026, 5, 7, 12, tzinfo=UTC)
        record = make_record(application_deadline="05.05.2026 18:00", auction_date="07.05.2026 10:00")
        record.enrichment_requested_at = datetime(2026, 5, 6, tzinfo=UTC)
        record.actuality_checked_at = None
        session = FakeSweepSession(scalar_batches=[[record], []])

        from unittest.mock import AsyncMock, patch

        with patch("app.services.lot_actuality.bump_auction_lot_dataset_version", AsyncMock()) as bump_dataset_version:
            result = asyncio.run(
                run_lot_actuality_sweep(
                    session,
                    limit=10,
                    current_time=current_time,
                )
            )

        bump_dataset_version.assert_awaited_once()
        self.assertEqual(result.candidate_count, 1)
        self.assertEqual(result.processed_count, 1)
        self.assertEqual(result.active_to_non_active_count, 1)
        self.assertEqual(result.non_active_to_active_count, 0)
        self.assertEqual(result.updated_count, 1)
        self.assertEqual(record.lifecycle_status, "expired")
        self.assertEqual(record.archived_at, current_time)
        self.assertEqual(record.archive_reason, "application_deadline_passed")
        self.assertIsNone(record.enrichment_requested_at)

    def test_run_lot_actuality_sweep_keeps_fresh_records_active_and_bumps_row_updated(self) -> None:
        current_time = datetime(2026, 5, 7, 12, tzinfo=UTC)
        record = make_record(application_deadline="08.05.2026 18:00", auction_date="10.05.2026 10:00")
        record.actuality_checked_at = None
        session = FakeSweepSession(scalar_batches=[[record], []])

        from unittest.mock import AsyncMock, patch

        with patch("app.services.lot_actuality.bump_auction_lot_dataset_version", AsyncMock()) as bump_dataset_version:
            result = asyncio.run(
                run_lot_actuality_sweep(
                    session,
                    limit=10,
                    current_time=current_time,
                )
            )

        bump_dataset_version.assert_awaited_once()
        self.assertEqual(bump_dataset_version.await_args.kwargs["event_type"], "row_updated")
        self.assertEqual(bump_dataset_version.await_args.kwargs["payload"]["changed_fields"], ["actuality_checked_at"])
        self.assertEqual(result.candidate_count, 1)
        self.assertEqual(result.processed_count, 1)
        self.assertEqual(result.active_to_non_active_count, 0)
        self.assertEqual(record.lifecycle_status, "active")
        self.assertIsNone(record.archived_at)
        self.assertIsNone(record.archive_reason)

    def test_actuality_sweep_prioritizes_high_rated_records_in_sql_order(self) -> None:
        current_time = datetime(2026, 5, 7, 12, tzinfo=UTC)
        session = FakeSweepSession()

        import asyncio

        asyncio.run(
            _list_actuality_sweep_candidates(
                session,
                current_time=current_time,
                limit=10,
                grace=timedelta(hours=24),
                stale_after=timedelta(days=30),
            )
        )

        self.assertTrue(session.scalars_calls)
        self.assertIn("ORDER BY auction_lot_records.rating_score DESC", str(session.scalars_calls[0]))


if __name__ == "__main__":
    unittest.main()
