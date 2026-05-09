from __future__ import annotations

import unittest
from urllib.error import HTTPError
from unittest.mock import AsyncMock, patch

from app.worker import auction_analysis_worker
from app.worker import auction_sync_worker
from app.worker.auction_sync_worker import _source_sync_error_payload, calculate_next_sync_delay
from app.worker.safety import DEFAULT_MIN_WORKER_POLL_INTERVAL_SECONDS


class AuctionSyncWorkerTests(unittest.TestCase):
    def test_calculate_next_sync_delay_without_jitter(self) -> None:
        self.assertEqual(calculate_next_sync_delay(10_800, 0), 10_800.0)

    def test_calculate_next_sync_delay_applies_bounded_jitter(self) -> None:
        self.assertEqual(
            calculate_next_sync_delay(10_800, 900, random_fraction=lambda: 0),
            9_900.0,
        )
        self.assertEqual(
            calculate_next_sync_delay(10_800, 900, random_fraction=lambda: 0.5),
            10_800.0,
        )
        self.assertEqual(
            calculate_next_sync_delay(10_800, 900, random_fraction=lambda: 1),
            11_700.0,
        )

    def test_calculate_next_sync_delay_never_returns_less_than_safe_minimum(self) -> None:
        self.assertEqual(
            calculate_next_sync_delay(0, 900, random_fraction=lambda: 0),
            DEFAULT_MIN_WORKER_POLL_INTERVAL_SECONDS,
        )
        self.assertEqual(
            calculate_next_sync_delay(-10, 0),
            DEFAULT_MIN_WORKER_POLL_INTERVAL_SECONDS,
        )

    def test_analysis_worker_delay_never_returns_zero(self) -> None:
        self.assertEqual(
            auction_analysis_worker.calculate_analysis_worker_delay(0),
            DEFAULT_MIN_WORKER_POLL_INTERVAL_SECONDS,
        )
        self.assertEqual(
            auction_analysis_worker.calculate_analysis_worker_delay(-30),
            DEFAULT_MIN_WORKER_POLL_INTERVAL_SECONDS,
        )

    def test_source_sync_error_payload_classifies_403_as_expected_source_error(self) -> None:
        error = HTTPError("https://tbankrot.ru/", 403, "Forbidden", hdrs=None, fp=None)

        payload = _source_sync_error_payload(source="tbankrot", error=error)

        self.assertTrue(payload["expected"])
        self.assertEqual(payload["error_code"], "source_forbidden")
        self.assertEqual(payload["http_status"], 403)
        self.assertFalse(payload["retryable"])

    def test_worker_main_handles_keyboard_interrupt(self) -> None:
        with (
            patch.object(auction_sync_worker, "run_worker", new=lambda: None),
            patch.object(auction_sync_worker.asyncio, "run", side_effect=KeyboardInterrupt),
        ):
            auction_sync_worker.main()

    def test_analysis_worker_main_handles_keyboard_interrupt(self) -> None:
        from unittest.mock import patch

        with (
            patch.object(auction_analysis_worker, "run_worker", new=lambda: None),
            patch.object(auction_analysis_worker.asyncio, "run", side_effect=KeyboardInterrupt),
        ):
            auction_analysis_worker.main()

    def test_visible_score_payload_ignores_non_scoring_row_changes(self) -> None:
        first = {
            "rating": {"score": 80, "level": "high", "breakdown": {"caps": []}},
            "analysis": {"status": "interesting"},
            "freshness": {"last_seen_at": "2026-04-30T00:00:00Z"},
        }
        second = {
            "rating": {"score": 80, "level": "high", "breakdown": {"caps": []}},
            "analysis": {"status": "interesting"},
            "freshness": {"last_seen_at": "2026-04-30T01:00:00Z"},
        }

        self.assertEqual(
            auction_analysis_worker._visible_score_payload(first),
            auction_analysis_worker._visible_score_payload(second),
        )

    def test_visible_score_payload_detects_rating_breakdown_changes(self) -> None:
        before = {"rating": {"score": 80, "breakdown": {"caps": []}}, "analysis": {"status": "interesting"}}
        after = {
            "rating": {"score": 80, "breakdown": {"caps": [{"key": "high_legal_risk"}]}},
            "analysis": {"status": "interesting"},
        }

        self.assertNotEqual(
            auction_analysis_worker._visible_score_payload(before),
            auction_analysis_worker._visible_score_payload(after),
        )


class AuctionSyncWorkerAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_sync_worker_sleeps_and_skips_sync(self) -> None:
        with (
            patch.object(auction_sync_worker.settings, "auction_sync_enabled", False),
            patch.object(auction_sync_worker.settings, "auction_sync_run_on_start", True),
            patch.object(auction_sync_worker.settings, "auction_sync_interval_seconds", 0),
            patch.object(auction_sync_worker.settings, "auction_sync_interval_jitter_seconds", 0),
            patch("app.worker.auction_sync_worker.sync_all_sources", AsyncMock()) as sync_all_sources,
            patch("app.worker.auction_sync_worker.asyncio.sleep", AsyncMock()) as sleep,
        ):
            await auction_sync_worker.run_worker(run_once=True)

        sync_all_sources.assert_not_awaited()
        sleep.assert_awaited_once_with(DEFAULT_MIN_WORKER_POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    unittest.main()
