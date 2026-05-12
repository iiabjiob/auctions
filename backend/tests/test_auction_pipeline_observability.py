from __future__ import annotations

import unittest
from types import SimpleNamespace
from datetime import UTC, datetime

from sqlalchemy.dialects import postgresql

from app.services.auction_pipeline_observability import (
    AuctionPipelineHealthResponse,
    build_auction_source_sync_status,
    build_auction_pipeline_counters_statement,
    get_auction_pipeline_counters,
)


class AuctionPipelineObservabilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_pipeline_counter_service_maps_aggregate_row(self) -> None:
        source_state = SimpleNamespace(
            code="tbankrot",
            title="TBankrot",
            enabled=True,
            sync_cursor={
                "last_sync_started_at": "2026-05-07T12:00:00+00:00",
                "last_sync_completed_at": "2026-05-07T12:05:00+00:00",
                "next_sync_not_before": "2026-05-07T13:00:00+00:00",
                "next_sync_not_after": "2026-05-07T13:15:00+00:00",
                "last_sync_error": "temporary failure",
            },
        )

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

            async def scalars(self, statement):  # noqa: ANN001
                class FakeScalars:
                    def all(self_inner):
                        return [source_state]

                return FakeScalars()

        counters = await get_auction_pipeline_counters(FakeSession())

        self.assertIsInstance(counters, AuctionPipelineHealthResponse)
        self.assertEqual(counters.counters.enrichment_requested, 4)
        self.assertEqual(counters.counters.enrichment_due_now, 2)
        self.assertEqual(counters.counters.enrichment_claimed_active, 1)
        self.assertEqual(counters.counters.enrichment_retry_waiting, 3)
        self.assertEqual(counters.counters.enrichment_failed_with_error, 1)
        self.assertEqual(counters.counters.enrichment_maxed_out, 2)
        self.assertEqual(counters.counters.scoring_stale_or_incomplete, 5)
        self.assertEqual(counters.counters.scored_current, 9)
        self.assertEqual(len(counters.sources), 1)
        self.assertEqual(counters.sources[0].code, "tbankrot")
        self.assertEqual(counters.sources[0].last_sync_error, "temporary failure")
        self.assertEqual(counters.sources[0].last_sync_started_at, datetime.fromisoformat("2026-05-07T12:00:00+00:00"))
        self.assertEqual(counters.sources[0].next_sync_not_before, datetime.fromisoformat("2026-05-07T13:00:00+00:00"))
        self.assertEqual(counters.sources[0].next_sync_not_after, datetime.fromisoformat("2026-05-07T13:15:00+00:00"))

    def test_build_auction_source_sync_status_parses_cursor_fields(self) -> None:
        source_state = SimpleNamespace(
            code="tbankrot",
            title="TBankrot",
            enabled=True,
            sync_cursor={
                "last_sync_started_at": "2026-05-07T12:00:00+00:00",
                "last_sync_completed_at": "2026-05-07T12:05:00+00:00",
                "next_sync_not_before": "2026-05-07T13:00:00+00:00",
                "next_sync_not_after": "2026-05-07T13:15:00+00:00",
                "last_sync_error": "temporary failure",
            },
        )

        status = build_auction_source_sync_status(source_state)

        self.assertEqual(status.code, "tbankrot")
        self.assertEqual(status.last_sync_started_at, datetime.fromisoformat("2026-05-07T12:00:00+00:00"))
        self.assertEqual(status.last_sync_completed_at, datetime.fromisoformat("2026-05-07T12:05:00+00:00"))
        self.assertEqual(status.next_sync_not_before, datetime.fromisoformat("2026-05-07T13:00:00+00:00"))
        self.assertEqual(status.next_sync_not_after, datetime.fromisoformat("2026-05-07T13:15:00+00:00"))
        self.assertEqual(status.last_sync_error, "temporary failure")

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
