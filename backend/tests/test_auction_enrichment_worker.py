from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from app.services.lot_enrichment import LotEnrichmentExecutionResult
from app.worker import auction_enrichment_worker


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
        }

        fake_session = object()
        fake_context = FakeSessionContext(fake_session)

        with (
            patch("app.worker.auction_enrichment_worker.AsyncSessionLocal", return_value=fake_context),
            patch(
                "app.worker.auction_enrichment_worker.execute_lot_enrichment_candidates",
                AsyncMock(return_value=LotEnrichmentExecutionResult(**result_payload)),
            ) as execute_enrichment,
            patch("app.services.auction_workspace.ensure_lot_detail_cache", AsyncMock()) as fetch_detail,
        ):
            result = await auction_enrichment_worker.run_enrichment_batch()

        execute_enrichment.assert_awaited_once_with(fake_session, limit=50)
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
        }

        with patch(
            "app.worker.auction_enrichment_worker.run_enrichment_batch",
            AsyncMock(return_value=result_payload),
        ) as run_batch:
            result = await auction_enrichment_worker.run_worker(run_once=True)

        run_batch.assert_awaited_once()
        self.assertEqual(result, result_payload)


if __name__ == "__main__":
    unittest.main()
