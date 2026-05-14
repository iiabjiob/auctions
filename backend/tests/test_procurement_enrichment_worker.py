from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from app.services.procurement_enrichment import ProcurementEnrichmentExecutionResult
from app.worker import procurement_enrichment_worker
from app.worker.safety import DEFAULT_MIN_WORKER_POLL_INTERVAL_SECONDS


class FakeSessionContext:
    def __init__(self, session) -> None:
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return None


class ProcurementEnrichmentWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_enrichment_batch_executes_candidates_and_commits(self) -> None:
        result_payload = {
            "candidate_count": 1,
            "processed_count": 1,
            "fetched_count": 1,
            "updated_count": 1,
            "still_missing_count": 0,
            "skipped_count": 0,
            "candidate_record_ids": [1],
            "completed_record_ids": [],
        }
        fake_session = AsyncMock()
        fake_context = FakeSessionContext(fake_session)

        with (
            patch("app.worker.procurement_enrichment_worker.AsyncSessionLocal", return_value=fake_context),
            patch(
                "app.worker.procurement_enrichment_worker.execute_procurement_enrichment_candidates",
                AsyncMock(return_value=ProcurementEnrichmentExecutionResult(**result_payload)),
            ) as execute_enrichment,
            patch.object(procurement_enrichment_worker.settings, "procurement_enrichment_item_pause_seconds", 0.0),
            patch.object(procurement_enrichment_worker.settings, "procurement_enrichment_batch_size", 25),
        ):
            result = await procurement_enrichment_worker.run_enrichment_batch()

        execute_enrichment.assert_awaited_once_with(fake_session, limit=25, item_pause_seconds=0.0)
        fake_session.commit.assert_awaited_once()
        self.assertEqual(result, result_payload)

    async def test_worker_run_once_returns_none_when_disabled(self) -> None:
        with patch.object(procurement_enrichment_worker.settings, "procurement_enrichment_enabled", False):
            result = await procurement_enrichment_worker.run_worker(run_once=True)

        self.assertIsNone(result)

    def test_enrichment_delay_never_returns_less_than_safe_minimum(self) -> None:
        self.assertEqual(
            procurement_enrichment_worker.calculate_procurement_enrichment_worker_delay(
                interval_seconds=0,
                empty_pause_seconds=0,
            ),
            DEFAULT_MIN_WORKER_POLL_INTERVAL_SECONDS,
        )

    def test_empty_enrichment_delay_uses_longer_empty_pause(self) -> None:
        self.assertEqual(
            procurement_enrichment_worker.calculate_procurement_enrichment_worker_delay(
                {"candidate_count": 0},
                interval_seconds=10,
                empty_pause_seconds=90,
            ),
            90.0,
        )


if __name__ == "__main__":
    unittest.main()
