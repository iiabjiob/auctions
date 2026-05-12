from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

from app.models.auction import AuctionLotDetailCache, AuctionLotRecord
from app.services.lot_enrichment import schedule_priority_lot_enrichment


def make_record(
    *,
    record_id: int,
    rating_score: int,
    application_deadline: str,
    lifecycle_status: str = "active",
    requested_at: datetime | None = None,
    claim_expires_at: datetime | None = None,
    next_retry_at: datetime | None = None,
) -> AuctionLotRecord:
    record = AuctionLotRecord(
        id=record_id,
        source_code="tbankrot",
        auction_external_id=f"auction-{record_id}",
        lot_external_id=f"lot-{record_id}",
        content_hash=f"content-{record_id}",
        datagrid_row={"application_deadline": application_deadline},
        normalized_item={"auction": {"application_deadline": application_deadline}},
    )
    record.rating_score = rating_score
    record.lifecycle_status = lifecycle_status
    record.enrichment_requested_at = requested_at
    record.enrichment_claimed_at = None if claim_expires_at is None else claim_expires_at - timedelta(minutes=5)
    record.enrichment_claim_expires_at = claim_expires_at
    record.next_enrichment_attempt_at = next_retry_at
    record.enrichment_attempt_count = 0
    return record


def make_detail_cache(*, record_id: int, fetched_at: datetime | None) -> AuctionLotDetailCache:
    cache = AuctionLotDetailCache(
        lot_record_id=record_id,
        content_hash=f"detail-{record_id}",
        lot_detail={"lot": {"description": "test"}},
        auction_detail={"auction": {"publication_date": "01.05.2026"}},
        documents=[],
    )
    if fetched_at is not None:
        cache.fetched_at = fetched_at
    return cache


class FakeScalarResult:
    def __init__(self, items: list[object]) -> None:
        self._items = list(items)

    def all(self) -> list[object]:
        return list(self._items)


class FakeSession:
    def __init__(
        self,
        *,
        top_ranked_records: list[AuctionLotRecord] | None = None,
        deadline_records: list[AuctionLotRecord] | None = None,
        detail_caches: list[AuctionLotDetailCache] | None = None,
    ) -> None:
        self.top_ranked_records = list(top_ranked_records or [])
        self.deadline_records = list(deadline_records or [])
        self.detail_caches = list(detail_caches or [])
        self.flush = AsyncMock()
        self.statements: list[object] = []

    async def scalars(self, statement):  # noqa: ANN001
        self.statements.append(statement)
        sql = str(statement)
        if "auction_lot_detail_caches" in sql:
            return FakeScalarResult(self.detail_caches)
        if "application_deadline_at ASC" in sql or "auction_at ASC" in sql:
            records = self.deadline_records
        else:
            records = self.top_ranked_records
        active_records = [record for record in records if getattr(record, "lifecycle_status", "active") == "active"]
        return FakeScalarResult(active_records)


class PriorityLotEnrichmentSchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def test_scheduler_schedules_stale_top_30_cache(self) -> None:
        current_time = datetime(2026, 5, 7, tzinfo=UTC)
        record = make_record(
            record_id=1,
            rating_score=95,
            application_deadline="08.05.2026 10:00",
        )
        detail_cache = make_detail_cache(record_id=1, fetched_at=current_time - timedelta(days=2))
        session = FakeSession(top_ranked_records=[record], deadline_records=[record], detail_caches=[detail_cache])

        result = await schedule_priority_lot_enrichment(session, current_time=current_time)

        self.assertEqual(result.candidate_count, 1)
        self.assertEqual(result.scheduled_count, 1)
        self.assertEqual(result.scheduled_record_ids, [1])
        self.assertEqual(record.enrichment_requested_at, current_time)
        session.flush.assert_awaited_once()

    async def test_scheduler_skips_fresh_cache(self) -> None:
        current_time = datetime(2026, 5, 7, tzinfo=UTC)
        record = make_record(
            record_id=1,
            rating_score=95,
            application_deadline="08.05.2026 10:00",
        )
        detail_cache = make_detail_cache(record_id=1, fetched_at=current_time - timedelta(hours=6))
        session = FakeSession(top_ranked_records=[record], deadline_records=[record], detail_caches=[detail_cache])

        result = await schedule_priority_lot_enrichment(session, current_time=current_time)

        self.assertEqual(result.candidate_count, 1)
        self.assertEqual(result.scheduled_count, 0)
        self.assertIsNone(record.enrichment_requested_at)
        session.flush.assert_awaited_once()

    async def test_scheduler_refreshes_top_30_trading_window_after_twelve_hours(self) -> None:
        current_time = datetime(2026, 5, 7, tzinfo=UTC)
        record = make_record(
            record_id=1,
            rating_score=95,
            application_deadline="08.05.2026 10:00",
        )
        detail_cache = make_detail_cache(record_id=1, fetched_at=current_time - timedelta(hours=13))
        session = FakeSession(top_ranked_records=[record], deadline_records=[record], detail_caches=[detail_cache])

        result = await schedule_priority_lot_enrichment(session, current_time=current_time)

        self.assertEqual(result.candidate_count, 1)
        self.assertEqual(result.scheduled_count, 1)
        self.assertEqual(record.enrichment_requested_at, current_time)
        session.flush.assert_awaited_once()

    async def test_scheduler_skips_archived_and_expired_records(self) -> None:
        current_time = datetime(2026, 5, 7, tzinfo=UTC)
        archived = make_record(
            record_id=1,
            rating_score=95,
            application_deadline="08.05.2026 10:00",
            lifecycle_status="archived",
        )
        expired = make_record(
            record_id=2,
            rating_score=90,
            application_deadline="08.05.2026 10:00",
            lifecycle_status="expired",
        )
        stale_archived = make_detail_cache(record_id=1, fetched_at=current_time - timedelta(days=4))
        stale_expired = make_detail_cache(record_id=2, fetched_at=current_time - timedelta(days=4))
        session = FakeSession(
            top_ranked_records=[archived, expired],
            deadline_records=[archived, expired],
            detail_caches=[stale_archived, stale_expired],
        )

        result = await schedule_priority_lot_enrichment(session, current_time=current_time)

        self.assertEqual(result.candidate_count, 0)
        self.assertEqual(result.scheduled_count, 0)
        self.assertTrue(any("auction_lot_records.lifecycle_status" in str(statement) for statement in session.statements))
        self.assertTrue(all(record.enrichment_requested_at is None for record in (archived, expired)))
        session.flush.assert_awaited_once()

    async def test_scheduler_schedules_near_deadline_low_score_record(self) -> None:
        current_time = datetime(2026, 5, 7, tzinfo=UTC)
        record = make_record(
            record_id=1,
            rating_score=5,
            application_deadline="07.05.2026 10:00",
        )
        detail_cache = make_detail_cache(record_id=1, fetched_at=current_time - timedelta(days=1))
        session = FakeSession(top_ranked_records=[], deadline_records=[record], detail_caches=[detail_cache])

        result = await schedule_priority_lot_enrichment(session, current_time=current_time)

        self.assertEqual(result.candidate_count, 1)
        self.assertEqual(result.scheduled_count, 1)
        self.assertEqual(result.scheduled_record_ids, [1])
        self.assertEqual(record.enrichment_requested_at, current_time)
        session.flush.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
