from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from app.services.lot_enrichment import LotEnrichmentExecutionResult
from app.worker import auction_enrichment_worker
from app.worker.safety import DEFAULT_MIN_WORKER_POLL_INTERVAL_SECONDS


class FakeSessionContext:
    def __init__(self, session) -> None:
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return None


class AuctionEnrichmentWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_enrichment_batch_uses_candidate_scan_without_detail_fetches(self) -> None:
        result_payload = {
            "candidate_count": 1,
            "processed_count": 1,
            "fetched_count": 1,
            "cleared_count": 1,
            "still_missing_count": 0,
            "skipped_count": 0,
            "candidate_record_ids": [1],
            "completed_record_ids": [],
        }

        fake_session = AsyncMock()
        fake_context = FakeSessionContext(fake_session)

        with (
            patch("app.worker.auction_enrichment_worker.AsyncSessionLocal", return_value=fake_context),
            patch(
                "app.worker.auction_enrichment_worker.schedule_priority_lot_enrichment",
                AsyncMock(return_value=None),
            ) as schedule_priority,
            patch(
                "app.worker.auction_enrichment_worker.execute_lot_enrichment_candidates",
                AsyncMock(return_value=LotEnrichmentExecutionResult(**result_payload)),
            ) as execute_enrichment,
            patch("app.services.auction_workspace.ensure_lot_detail_cache", AsyncMock()) as fetch_detail,
            patch.object(auction_enrichment_worker.settings, "auction_enrichment_item_pause_seconds", 0.0),
        ):
            result = await auction_enrichment_worker.run_enrichment_batch()

        schedule_priority.assert_awaited_once_with(fake_session)
        execute_enrichment.assert_awaited_once_with(fake_session, limit=50, item_pause_seconds=0.0)
        fake_session.commit.assert_awaited_once()
        fetch_detail.assert_not_called()
        self.assertEqual(result, result_payload)

    async def test_worker_run_once_returns_batch_result(self) -> None:
        result_payload = {
            "candidate_count": 0,
            "processed_count": 0,
            "fetched_count": 0,
            "cleared_count": 0,
            "still_missing_count": 0,
            "skipped_count": 0,
            "candidate_record_ids": [],
            "completed_record_ids": [],
        }

        with patch(
            "app.worker.auction_enrichment_worker.run_enrichment_batch",
            AsyncMock(return_value=result_payload),
        ) as run_batch:
            result = await auction_enrichment_worker.run_worker(run_once=True)

        run_batch.assert_awaited_once()
        self.assertEqual(result, result_payload)

    def test_enrichment_delay_never_returns_less_than_safe_minimum(self) -> None:
        self.assertEqual(
            auction_enrichment_worker.calculate_enrichment_worker_delay(
                interval_seconds=0,
                empty_pause_seconds=0,
            ),
            DEFAULT_MIN_WORKER_POLL_INTERVAL_SECONDS,
        )

    def test_empty_enrichment_delay_uses_longer_empty_pause(self) -> None:
        self.assertEqual(
            auction_enrichment_worker.calculate_enrichment_worker_delay(
                {"candidate_count": 0},
                interval_seconds=10,
                empty_pause_seconds=90,
            ),
            90.0,
        )

    def test_enrichment_failure_delay_is_exponential(self) -> None:
        self.assertEqual(
            auction_enrichment_worker.calculate_enrichment_worker_delay(
                interval_seconds=10,
                empty_pause_seconds=90,
                failure_count=3,
            ),
            40.0,
        )


if __name__ == "__main__":
    unittest.main()
