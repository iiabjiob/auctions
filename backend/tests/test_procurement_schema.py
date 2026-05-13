from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.models.procurement import ProcurementLotRecord


class ProcurementSchemaTests(unittest.TestCase):
    def test_procurement_lot_record_has_v1_decision_fields(self) -> None:
        columns = ProcurementLotRecord.__table__.c

        for column_name in (
            "workflow_status",
            "assignee",
            "comment",
            "final_decision",
            "rejection_reason",
            "category",
            "matched_keywords",
            "excluded_keywords",
            "filter_reason",
            "customer_inn",
            "delivery_region",
            "delivery_address",
            "specification_url",
            "documents_url",
            "certificate_requirements",
            "documentation_present",
            "bid_security_amount",
            "contract_security_amount",
            "prepayment_percent",
            "payment_terms",
            "quantity",
            "unit_nmck",
            "cost_realistic",
            "cost_cautious",
            "net_profit",
            "profitability",
            "roi",
            "cash_gap_peak",
        ):
            self.assertIn(column_name, columns)

        self.assertFalse(columns.workflow_status.nullable)
        self.assertFalse(columns.matched_keywords.nullable)
        self.assertFalse(columns.excluded_keywords.nullable)

    def test_procurement_lot_record_table_compiles_for_postgres(self) -> None:
        ddl = str(CreateTable(ProcurementLotRecord.__table__).compile(dialect=postgresql.dialect()))

        self.assertIn("workflow_status", ddl)
        self.assertIn("matched_keywords JSONB", ddl)
        self.assertIn("profitability NUMERIC(10, 6)", ddl)

    def test_procurement_search_text_includes_v1_fields(self) -> None:
        record = ProcurementLotRecord(
            source_code="zakupki",
            external_id="123",
            registry_number="123",
            content_hash="hash",
            workflow_status="review",
            category="Спецодежда",
            title="Поставка спецодежды",
            customer_name="Заказчик",
            customer_inn="7700000000",
            delivery_region="Москва",
            normalized_item={},
            raw_item={},
        )

        from app.models.procurement import _sync_procurement_lot_search_text

        _sync_procurement_lot_search_text(None, None, record)

        self.assertIn("Спецодежда", record.search_text or "")
        self.assertIn("7700000000", record.search_text or "")
        self.assertIn("review", record.search_text or "")

    def test_expand_procurement_migration_follows_current_head(self) -> None:
        migration_path = Path("alembic/versions/202605130011_expand_procurement_v1_fields.py")
        spec = importlib.util.spec_from_file_location("procurement_v1_migration", migration_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        self.assertEqual(module.revision, "202605130011")
        self.assertEqual(module.down_revision, "202605130010")
