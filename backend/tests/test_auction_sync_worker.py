from __future__ import annotations

import unittest

from app.worker.auction_sync_worker import calculate_next_sync_delay


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

    def test_calculate_next_sync_delay_never_returns_less_than_one_second(self) -> None:
        self.assertEqual(calculate_next_sync_delay(0, 900, random_fraction=lambda: 0), 1.0)


if __name__ == "__main__":
    unittest.main()
