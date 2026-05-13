from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.models.procurement import ProcurementLotRecord
from app.services.procurement_scoring import PROCUREMENT_SCORING_VERSION, apply_procurement_score, score_procurement_record


NOW = datetime(2026, 5, 13, 12, tzinfo=UTC)


def make_record(**overrides) -> ProcurementLotRecord:  # noqa: ANN003
    values = {
        "source_code": "zakupki",
        "external_id": "123",
        "registry_number": "0123456789",
        "law": "44-ФЗ",
        "title": "Поставка спецодежды",
        "status": "Подача заявок",
        "customer_name": "ГБУ Заказчик",
        "customer_inn": "7700000000",
        "procedure_type": "Электронный аукцион",
        "platform_name": "ЕИС",
        "initial_price_value": Decimal("2000000"),
        "application_deadline_at": NOW + timedelta(days=10),
        "documents_url": "https://example.test/docs",
        "certificate_requirements": "ТР ТС 019/2011",
        "documentation_present": True,
        "category": "Спецодежда",
        "matched_keywords": ["спецодежда"],
        "excluded_keywords": [],
        "quantity": Decimal("1000"),
        "unit_nmck": Decimal("2000"),
        "net_profit": Decimal("650000"),
        "profitability": Decimal("0.32"),
        "roi": Decimal("0.55"),
        "cash_gap_peak": Decimal("300000"),
        "calculator_scenarios": {"cautious": {"complete": True}},
        "content_hash": "hash",
        "attractiveness_score": 0,
        "attractiveness_level": "reject",
        "attractiveness_reasons": [],
        "normalized_item": {},
        "raw_item": {},
    }
    values.update(overrides)
    return ProcurementLotRecord(**values)


class ProcurementScoringTests(unittest.TestCase):
    def test_high_profit_valid_tender_is_priority_and_persists_metadata(self) -> None:
        record = make_record()

        result = apply_procurement_score(record, current_time=NOW)

        self.assertGreaterEqual(result.attractiveness.score, 80)
        self.assertEqual(result.attractiveness.level, "priority")
        self.assertEqual(record.scoring_version, PROCUREMENT_SCORING_VERSION)
        self.assertEqual(record.scoring_input_hash, result.input_hash)
        self.assertEqual(record.scored_at, NOW)
        self.assertIn("маржинальность выше 25%", record.attractiveness_reasons)

    def test_excluded_tender_is_capped_to_reject(self) -> None:
        record = make_record(excluded_keywords=["ботинки"], filter_reason="excluded_keyword:ботинки")

        result = score_procurement_record(record, current_time=NOW)

        self.assertLessEqual(result.attractiveness.score, 25)
        self.assertEqual(result.attractiveness.level, "reject")
        self.assertTrue(any("исключающие ключевые слова" in reason for reason in result.attractiveness.reasons))

    def test_missing_documentation_degrades_score(self) -> None:
        record = make_record(documentation_present=False, documents_url=None, specification_url=None)

        result = score_procurement_record(record, current_time=NOW)

        self.assertLess(result.attractiveness.score, 80)
        self.assertIn("штраф за отсутствие документации", result.attractiveness.reasons)

    def test_urgent_deadline_degrades_score(self) -> None:
        record = make_record(application_deadline_at=NOW + timedelta(hours=20))

        result = score_procurement_record(record, current_time=NOW)

        self.assertLess(result.attractiveness.score, 70)
        self.assertIn("штраф за срочный дедлайн", result.attractiveness.reasons)

    def test_no_calculation_falls_back_to_parser_heuristics(self) -> None:
        record = make_record(
            net_profit=None,
            profitability=None,
            roi=None,
            cash_gap_peak=None,
            calculator_scenarios={},
            initial_price_value=Decimal("1500000"),
        )

        result = score_procurement_record(record, current_time=NOW)

        self.assertGreaterEqual(result.attractiveness.score, 60)
        self.assertEqual(result.attractiveness.level, "watch")
        self.assertTrue(any("нет расчета" in reason for reason in result.attractiveness.reasons))


if __name__ == "__main__":
    unittest.main()
