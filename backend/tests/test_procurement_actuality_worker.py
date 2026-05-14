from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from app.services.procurement_actuality import ProcurementActualitySweepResult
from app.worker import procurement_actuality_worker
from app.worker.safety import DEFAULT_MIN_WORKER_POLL_INTERVAL_SECONDS


class FakeSessionContext:
    def __init__(self, session) -> None:
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return None


class ProcurementActualityWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_actuality_sweep_batch_uses_session_and_commits(self) -> None:
        fake_session = AsyncMock()
        fake_context = FakeSessionContext(fake_session)
        result_payload = ProcurementActualitySweepResult(
            candidate_count=1,
            processed_count=1,
            updated_count=1,
            active_to_non_active_count=1,
            non_active_to_active_count=0,
            skipped_count=0,
            candidate_record_ids=[1],
        )

        with (
            patch("app.worker.procurement_actuality_worker.AsyncSessionLocal", return_value=fake_context),
            patch(
                "app.worker.procurement_actuality_worker.run_procurement_actuality_sweep",
                AsyncMock(return_value=result_payload),
            ) as run_sweep,
            patch.object(procurement_actuality_worker.settings, "procurement_actuality_sweep_batch_size", 25),
        ):
            result = await procurement_actuality_worker.run_actuality_sweep_batch()

        run_sweep.assert_awaited_once_with(fake_session, limit=25)
        fake_session.commit.assert_awaited_once()
        self.assertEqual(result, result_payload.model_dump(mode="json"))

    async def test_worker_run_once_returns_none_when_disabled(self) -> None:
        with patch.object(procurement_actuality_worker.settings, "procurement_actuality_sweep_enabled", False):
            result = await procurement_actuality_worker.run_worker(run_once=True)

        self.assertIsNone(result)

    def test_actuality_delay_never_returns_less_than_safe_minimum(self) -> None:
        self.assertEqual(
            procurement_actuality_worker.calculate_procurement_actuality_sweep_worker_delay(0),
            DEFAULT_MIN_WORKER_POLL_INTERVAL_SECONDS,
        )


if __name__ == "__main__":
    unittest.main()
