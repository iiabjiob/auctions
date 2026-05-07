from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from app.services.lot_enrichment import LotEnrichmentDryRunResult
from app.worker import auction_enrichment_worker


class FakeSessionContext:
    def __init__(self, session) -> None:
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return None


class AuctionEnrichmentWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_dry_run_worker_uses_candidate_scan_without_detail_fetches(self) -> None:
        result_payload = {
            "candidate_count": 1,
            "processed_count": 1,
            "needs_enrichment_count": 1,
            "ready_for_scoring_count": 0,
            "candidate_record_ids": [1],
            "candidate_row_ids": ["row-1"],
        }

        fake_session = object()
        fake_context = FakeSessionContext(fake_session)

        with (
            patch("app.worker.auction_enrichment_worker.AsyncSessionLocal", return_value=fake_context),
            patch(
                "app.worker.auction_enrichment_worker.dry_run_lot_enrichment_candidates",
                AsyncMock(return_value=LotEnrichmentDryRunResult(**result_payload)),
            ) as dry_run,
            patch("app.services.auction_workspace.ensure_lot_detail_cache", AsyncMock()) as fetch_detail,
        ):
            result = await auction_enrichment_worker.run_worker()

        dry_run.assert_awaited_once_with(fake_session, limit=50)
        fetch_detail.assert_not_called()
        self.assertEqual(result, result_payload)


if __name__ == "__main__":
    unittest.main()
