from __future__ import annotations

import unittest
from types import SimpleNamespace

from sqlalchemy.dialects import postgresql

from app.services.auction_pipeline_observability import (
    build_auction_pipeline_counters_statement,
    get_auction_pipeline_counters,
)


class AuctionPipelineObservabilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_pipeline_counter_service_maps_aggregate_row(self) -> None:
        class FakeSession:
            def __init__(self):
                self.statement = None

            async def execute(self, statement):
                self.statement = statement
                return SimpleNamespace(
                    one=lambda: SimpleNamespace(
                        enrichment_requested=4,
                        enrichment_due_now=2,
                        enrichment_claimed_active=1,
                        enrichment_retry_waiting=3,
                        enrichment_failed_with_error=1,
                        enrichment_maxed_out=2,
                        scoring_stale_or_incomplete=5,
                        scored_current=9,
                    )
                )

        counters = await get_auction_pipeline_counters(FakeSession())

        self.assertEqual(counters.enrichment_requested, 4)
        self.assertEqual(counters.enrichment_due_now, 2)
        self.assertEqual(counters.enrichment_claimed_active, 1)
        self.assertEqual(counters.enrichment_retry_waiting, 3)
        self.assertEqual(counters.enrichment_failed_with_error, 1)
        self.assertEqual(counters.enrichment_maxed_out, 2)
        self.assertEqual(counters.scoring_stale_or_incomplete, 5)
        self.assertEqual(counters.scored_current, 9)

    def test_pipeline_counter_statement_contains_expected_filters(self) -> None:
        statement = build_auction_pipeline_counters_statement()
        sql = str(statement.compile(dialect=postgresql.dialect()))

        self.assertIn("enrichment_requested_at IS NOT NULL", sql)
        self.assertIn("next_enrichment_attempt_at", sql)
        self.assertIn("enrichment_claimed_at", sql)
        self.assertIn("last_enrichment_error", sql)
        self.assertIn("enrichment_attempt_count", sql)
        self.assertIn("scoring_version", sql)
        self.assertIn("score_input_hash", sql)
        self.assertIn("score_breakdown", sql)
        self.assertIn("scored_current", sql)
