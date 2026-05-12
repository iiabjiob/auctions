from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services.auction_workspace import reanalyze_lot_workspace, request_lot_workspace_live_refresh
from app.services.auction_workspace import find_lot_record


class AuctionWorkspaceManualRefreshTests(unittest.IsolatedAsyncioTestCase):
    async def test_find_lot_record_falls_back_to_lot_id_when_auction_id_misses(self) -> None:
        record = SimpleNamespace(id=1, lot_external_id="lot-1", auction_external_id="auction-1")
        session = SimpleNamespace(scalar=AsyncMock(side_effect=[None, record]))

        result = await find_lot_record(
            session,
            source="tbankrot",
            lot_id="lot-1",
            auction_id="wrong-auction",
        )

        self.assertIs(result, record)
        self.assertEqual(session.scalar.await_count, 2)

    async def test_live_refresh_queues_and_records_user_operation(self) -> None:
        record = SimpleNamespace(
            id=1,
            auction_external_id="auction-1",
            enrichment_requested_at=None,
            enrichment_requested_reason=None,
            last_enrichment_attempt_at=None,
            enrichment_attempt_count=0,
            next_enrichment_attempt_at=None,
            last_enrichment_error=None,
            enrichment_claimed_at=None,
            enrichment_claimed_by=None,
            enrichment_claim_expires_at=None,
        )
        session = SimpleNamespace(commit=AsyncMock())

        with (
            patch("app.services.auction_workspace.find_lot_record", AsyncMock(return_value=record)),
            patch("app.services.auction_workspace._latest_manual_refresh_at", AsyncMock(return_value=None)),
            patch("app.services.auction_workspace.record_grid_operation", AsyncMock()) as record_operation,
        ):
            response = await request_lot_workspace_live_refresh(
                session,
                source="tbankrot",
                lot_id="lot-1",
                auction_id="auction-1",
                user_id="user-1",
            )

        self.assertEqual(response.status, "queued")
        self.assertTrue(response.queued)
        self.assertIsNotNone(response.next_allowed_at)
        self.assertEqual(record.enrichment_requested_reason, "manual_live")
        self.assertEqual(record.enrichment_attempt_count, 0)
        session.commit.assert_awaited_once()
        record_operation.assert_awaited_once()
        self.assertEqual(response.current_enrichment_state.requested_reason, "manual_live")

    async def test_live_refresh_reports_already_pending_before_rate_limits(self) -> None:
        requested_at = datetime(2026, 5, 12, 10, tzinfo=UTC)
        record = SimpleNamespace(
            id=1,
            auction_external_id="auction-1",
            enrichment_requested_at=requested_at,
            enrichment_requested_reason="manual_live",
            last_enrichment_attempt_at=None,
            enrichment_attempt_count=0,
            next_enrichment_attempt_at=None,
            last_enrichment_error=None,
            enrichment_claimed_at=None,
            enrichment_claimed_by=None,
            enrichment_claim_expires_at=None,
        )
        session = SimpleNamespace(commit=AsyncMock())

        with (
            patch("app.services.auction_workspace.find_lot_record", AsyncMock(return_value=record)),
            patch("app.services.auction_workspace.record_grid_operation", AsyncMock()) as record_operation,
        ):
            response = await request_lot_workspace_live_refresh(
                session,
                source="tbankrot",
                lot_id="lot-1",
                auction_id="auction-1",
                user_id="user-1",
            )

        self.assertEqual(response.status, "already_pending")
        self.assertFalse(response.queued)
        self.assertEqual(response.next_allowed_at, requested_at + timedelta(minutes=30))
        record_operation.assert_not_called()
        session.commit.assert_not_awaited()

    async def test_live_refresh_reports_user_rate_limit(self) -> None:
        record = SimpleNamespace(
            id=1,
            auction_external_id="auction-1",
            enrichment_requested_at=None,
            enrichment_requested_reason=None,
            last_enrichment_attempt_at=None,
            enrichment_attempt_count=0,
            next_enrichment_attempt_at=None,
            last_enrichment_error=None,
            enrichment_claimed_at=None,
            enrichment_claimed_by=None,
            enrichment_claim_expires_at=None,
        )
        session = SimpleNamespace(commit=AsyncMock())

        class FixedDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                value = datetime(2026, 5, 12, 12, tzinfo=UTC)
                return value if tz is None else value.astimezone(tz)

        with (
            patch("app.services.auction_workspace.find_lot_record", AsyncMock(return_value=record)),
            patch("app.services.auction_workspace.datetime", FixedDateTime),
            patch(
                "app.services.auction_workspace._latest_manual_refresh_at",
                AsyncMock(side_effect=[None, datetime(2026, 5, 12, 11, 30, tzinfo=UTC)]),
            ),
            patch("app.services.auction_workspace.record_grid_operation", AsyncMock()) as record_operation,
        ):
            response = await request_lot_workspace_live_refresh(
                session,
                source="tbankrot",
                lot_id="lot-1",
                auction_id="auction-1",
                user_id="user-1",
            )

        self.assertEqual(response.status, "rate_limited")
        self.assertFalse(response.queued)
        self.assertEqual(response.next_allowed_at, datetime(2026, 5, 12, 12, 30, tzinfo=UTC))
        record_operation.assert_not_called()
        session.commit.assert_not_awaited()

    async def test_reanalyze_lot_workspace_recalculates_without_fetching_source(self) -> None:
        record = SimpleNamespace(id=1, source_code="tbankrot", lot_external_id="lot-1", auction_external_id="auction-1")
        detail_cache = SimpleNamespace(fetched_at=None)
        session = SimpleNamespace(commit=AsyncMock())
        runtime_config = SimpleNamespace(
            category_keywords={},
            exclusion_keywords=(),
            legal_risk_rules=SimpleNamespace(),
            owner_profile=SimpleNamespace(),
            dimension_weights=SimpleNamespace(),
        )

        with (
            patch("app.services.auction_workspace.find_lot_record", AsyncMock(return_value=record)),
            patch("app.services.auction_workspace.get_cached_lot_detail_cache", AsyncMock(return_value=detail_cache)),
            patch("app.services.auction_workspace.ensure_work_item", AsyncMock(return_value=SimpleNamespace(id=7))),
            patch("app.services.auction_workspace.auction_analysis_config_service.get_runtime_config", AsyncMock(return_value=runtime_config)),
            patch("app.services.auction_workspace.recalculate_record_rating"),
            patch("app.services.auction_workspace.update_record_search_text"),
            patch("app.services.auction_workspace.generate_and_persist_lot_decision_report_snapshot", AsyncMock()),
            patch("app.services.auction_workspace.bump_auction_lot_dataset_version", AsyncMock()),
            patch("app.services.auction_workspace.record_grid_operation", AsyncMock()) as record_operation,
            patch("app.services.auction_workspace._publish_row_updated", AsyncMock()),
            patch("app.services.auction_workspace.build_workspace_response", AsyncMock(return_value={"workspace": True})),
        ):
            response = await reanalyze_lot_workspace(
                session,
                source="tbankrot",
                lot_id="lot-1",
                auction_id="auction-1",
                user_id="user-1",
            )

        self.assertEqual(response, {"workspace": True})
        record_operation.assert_awaited_once()
        session.commit.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
