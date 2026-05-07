from __future__ import annotations

import unittest
from types import SimpleNamespace

from sqlalchemy.dialects import postgresql
from unittest.mock import AsyncMock, patch

from app.services.auction_analysis_config import auction_analysis_config_service
from app.services.auction_scoring_invalidation import invalidate_records_for_scoring_config_change


class FakeSession:
    def __init__(self, rowcount: int = 0) -> None:
        self.rowcount = rowcount
        self.executed = []

    async def execute(self, statement):
        self.executed.append(statement)
        return SimpleNamespace(rowcount=self.rowcount)


class AuctionAnalysisConfigInvalidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_scoring_config_change_invalidation_stales_identity_without_touching_score_payload(self) -> None:
        session = FakeSession(rowcount=3)

        affected = await invalidate_records_for_scoring_config_change(
            session,
            current_scoring_version="deterministic-v2",
        )

        self.assertEqual(affected, 3)
        statement = session.executed[0]
        sql = str(statement.compile(dialect=postgresql.dialect()))
        self.assertIn("scoring_version=%(scoring_version)s", sql)
        self.assertIn("score_input_hash=%(score_input_hash)s", sql)
        self.assertNotIn("rating_score", sql)
        self.assertNotIn("rating_level", sql)
        self.assertNotIn("score_breakdown", sql)

    async def test_queue_recalculation_delegates_to_scoring_config_invalidation(self) -> None:
        session = FakeSession(rowcount=5)

        with patch(
            "app.services.auction_analysis_config.invalidate_records_for_scoring_config_change",
            AsyncMock(return_value=5),
        ) as invalidate_records:
            affected = await auction_analysis_config_service.queue_recalculation(session)

        self.assertEqual(affected, 5)
        invalidate_records.assert_awaited_once_with(session, current_scoring_version="deterministic-v2")


if __name__ == "__main__":
    unittest.main()
