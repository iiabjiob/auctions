from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from app.models.procurement import ProcurementLotRecord
from app.services.procurement_enrichment import classify_procurement_enrichment, schedule_procurement_lot_enrichment


NOW = datetime(2026, 5, 14, 12, tzinfo=UTC)


def make_record(**overrides) -> ProcurementLotRecord:  # noqa: ANN003
    values = {
        "source_code": "zakupki",
        "external_id": "123",
        "registry_number": "123",
        "title": "Поставка спецодежды",
        "notice_url": "https://zakupki.gov.ru/epz/order/notice/common-info.html?regNumber=123",
        "documents_url": None,
        "specification_url": None,
        "documentation_present": False,
        "certificate_requirements": None,
        "payment_terms": None,
        "delivery_region": None,
        "delivery_address": None,
        "content_hash": "hash",
        "normalized_item": {},
        "raw_item": {},
    }
    values.update(overrides)
    return ProcurementLotRecord(**values)


class ProcurementEnrichmentTests(unittest.TestCase):
    def test_missing_detail_fields_require_enrichment(self) -> None:
        evaluation = classify_procurement_enrichment(make_record())

        self.assertTrue(evaluation.needs_enrichment)
        self.assertIn("documents", evaluation.missing_fields)
        self.assertEqual(evaluation.reason_category, "missing_procurement_detail")

    def test_complete_record_does_not_require_enrichment(self) -> None:
        evaluation = classify_procurement_enrichment(
            make_record(
                documents_url="https://zakupki.gov.ru/docs",
                documentation_present=True,
                certificate_requirements="ТР ТС 019/2011",
                payment_terms="30 дней",
                delivery_region="Москва",
            )
        )

        self.assertFalse(evaluation.needs_enrichment)

    def test_schedule_sets_requested_fields_and_preserves_existing_without_force(self) -> None:
        record = make_record(enrichment_requested_at=NOW - timedelta(hours=1))
        evaluation = classify_procurement_enrichment(record)

        changed = schedule_procurement_lot_enrichment(record, evaluation, requested_at=NOW)

        self.assertFalse(changed)
        self.assertEqual(record.enrichment_requested_at, NOW - timedelta(hours=1))

    def test_schedule_force_resets_retry_error(self) -> None:
        record = make_record(last_enrichment_error="timeout", next_enrichment_attempt_at=NOW + timedelta(hours=1))
        evaluation = classify_procurement_enrichment(record)

        changed = schedule_procurement_lot_enrichment(record, evaluation, requested_at=NOW, force=True)

        self.assertTrue(changed)
        self.assertEqual(record.enrichment_requested_at, NOW)
        self.assertIsNone(record.last_enrichment_error)
        self.assertIsNone(record.next_enrichment_attempt_at)


if __name__ == "__main__":
    unittest.main()
