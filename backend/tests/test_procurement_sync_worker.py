from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from app.worker import procurement_sync_worker


class ProcurementSyncWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_worker_keeps_process_alive_when_sync_cycle_times_out(self) -> None:
        with (
            patch.object(procurement_sync_worker.settings, "procurement_sync_enabled", True),
            patch.object(procurement_sync_worker.settings, "procurement_sync_run_on_start", True),
            patch.object(procurement_sync_worker.settings, "procurement_sync_limit", 100),
            patch("app.worker.procurement_sync_worker.AsyncSessionLocal"),
            patch(
                "app.worker.procurement_sync_worker.sync_enabled_procurement_sources",
                AsyncMock(side_effect=TimeoutError("timed out")),
            ) as sync_sources,
        ):
            await procurement_sync_worker.run_worker(run_once=True)

        sync_sources.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
