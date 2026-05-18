from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

from app.models.procurement import ProcurementLotRecord
from app.services.procurement_actuality import (
    classify_procurement_actuality,
    parse_procurement_datetime,
    run_procurement_actuality_sweep,
)
from app.services.procurement_sync import _sync_procurement_record_actuality


NOW = datetime(2026, 5, 14, 12, tzinfo=UTC)


def make_record(**overrides) -> ProcurementLotRecord:  # noqa: ANN003
    values = {
        "id": 1,
        "source_code": "zakupki",
        "external_id": "123",
        "registry_number": "123",
        "title": "Поставка спецодежды",
        "status": "Подача заявок",
        "application_deadline_at": NOW + timedelta(days=3),
        "last_seen_at": NOW - timedelta(hours=1),
        "lifecycle_status": "active",
        "content_hash": "hash",
        "normalized_item": {},
        "raw_item": {},
    }
    values.update(overrides)
    return ProcurementLotRecord(**values)


class FakeScalarResult:
    def __init__(self, items: list[object]) -> None:
        self._items = items

    def all(self) -> list[object]:
        return list(self._items)


class FakeSweepSession:
    def __init__(self, items: list[object]) -> None:
        self.items = items
        self.scalars_calls: list[object] = []

    async def scalars(self, statement):  # noqa: ANN001
        self.scalars_calls.append(statement)
        return FakeScalarResult(self.items)


class ProcurementActualityTests(unittest.IsolatedAsyncioTestCase):
    def test_parse_procurement_datetime_supports_common_formats(self) -> None:
        self.assertEqual(parse_procurement_datetime("14.05.2026 18:00"), datetime(2026, 5, 14, 18, tzinfo=UTC))
        self.assertEqual(parse_procurement_datetime("2026-05-14T18:00:00+03:00"), datetime(2026, 5, 14, 15, tzinfo=UTC))
        self.assertIsNone(parse_procurement_datetime(None))

    def test_classify_active_when_deadline_future_and_seen_recently(self) -> None:
        classification = classify_procurement_actuality(make_record(), current_time=NOW)

        self.assertEqual(classification.lifecycle_status, "active")
        self.assertIsNone(classification.archive_reason)

    def test_classify_expired_when_deadline_passed(self) -> None:
        classification = classify_procurement_actuality(
            make_record(application_deadline_at=NOW - timedelta(days=2)),
            current_time=NOW,
        )

        self.assertEqual(classification.lifecycle_status, "expired")
        self.assertEqual(classification.archive_reason, "application_deadline_passed")

    def test_classify_archived_for_terminal_status(self) -> None:
        classification = classify_procurement_actuality(
            make_record(status="Закупка завершена", application_deadline_at=NOW + timedelta(days=3)),
            current_time=NOW,
        )

        self.assertEqual(classification.lifecycle_status, "archived")
        self.assertEqual(classification.archive_reason, "terminal_status")

    def test_classify_stale_when_last_seen_old(self) -> None:
        classification = classify_procurement_actuality(
            make_record(last_seen_at=NOW - timedelta(days=31), application_deadline_at=NOW + timedelta(days=10)),
            current_time=NOW,
        )

        self.assertEqual(classification.lifecycle_status, "stale")
        self.assertEqual(classification.archive_reason, "last_seen_too_old")

    async def test_sweep_marks_expired_and_bumps_row_deleted(self) -> None:
        record = make_record(application_deadline_at=NOW - timedelta(days=2), enrichment_requested_at=NOW)
        session = FakeSweepSession([record])

        with patch("app.services.procurement_actuality.bump_procurement_lot_dataset_version", AsyncMock()) as bump:
            result = await run_procurement_actuality_sweep(session, limit=10, current_time=NOW)

        self.assertEqual(result.candidate_count, 1)
        self.assertEqual(result.active_to_non_active_count, 1)
        self.assertEqual(record.lifecycle_status, "expired")
        self.assertIsNone(record.enrichment_requested_at)
        bump.assert_awaited_once()
        self.assertEqual(bump.await_args.kwargs["event_type"], "row_deleted")

    def test_sync_actuality_restores_reappeared_active_record(self) -> None:
        record = make_record(
            application_deadline_at=NOW + timedelta(days=5),
            lifecycle_status="expired",
            archived_at=NOW - timedelta(days=1),
            archive_reason="application_deadline_passed",
        )

        next_status = _sync_procurement_record_actuality(record, checked_at=NOW)

        self.assertEqual(next_status, "active")
        self.assertEqual(record.lifecycle_status, "active")
        self.assertIsNone(record.archived_at)
        self.assertIsNone(record.archive_reason)
        self.assertEqual(record.actuality_checked_at, NOW)


if __name__ == "__main__":
    unittest.main()
