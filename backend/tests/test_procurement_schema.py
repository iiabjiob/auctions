from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.models.procurement import (
    ProcurementLotDetailCache,
    ProcurementLotDetailObservation,
    ProcurementLotObservation,
    ProcurementLotRecord,
    ProcurementSourceHttpExchange,
    ProcurementSourceSyncRun,
    ProcurementSourceSyncState,
    ProcurementTelegramNotificationOutbox,
)


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
            "calculator_inputs",
            "calculator_scenarios",
            "scoring_version",
            "scoring_input_hash",
            "scored_at",
            "enrichment_requested_at",
            "enrichment_attempt_count",
            "next_enrichment_attempt_at",
            "last_enrichment_error",
            "lifecycle_status",
            "finished_at",
            "archived_at",
            "archive_reason",
            "actuality_checked_at",
        ):
            self.assertIn(column_name, columns)

        self.assertFalse(columns.workflow_status.nullable)
        self.assertFalse(columns.matched_keywords.nullable)
        self.assertFalse(columns.excluded_keywords.nullable)

    def test_procurement_lot_record_table_compiles_for_postgres(self) -> None:
        ddl = str(CreateTable(ProcurementLotRecord.__table__).compile(dialect=postgresql.dialect()))

        self.assertIn("workflow_status", ddl)
        self.assertIn("matched_keywords JSONB", ddl)
        self.assertIn("calculator_inputs JSONB", ddl)
        self.assertIn("scoring_version", ddl)
        self.assertIn("profitability NUMERIC(10, 6)", ddl)

    def test_procurement_telegram_outbox_table_compiles_for_postgres(self) -> None:
        ddl = str(CreateTable(ProcurementTelegramNotificationOutbox.__table__).compile(dialect=postgresql.dialect()))

        self.assertIn("procurement_lot_record_id INTEGER NOT NULL", ddl)
        self.assertIn("event_type VARCHAR(64) NOT NULL", ddl)
        self.assertIn("message_payload JSONB NOT NULL", ddl)
        self.assertIn("ck_procurement_telegram_outbox_status", ddl)

    def test_procurement_sync_diagnostic_tables_compile_for_postgres(self) -> None:
        state_ddl = str(CreateTable(ProcurementSourceSyncState.__table__).compile(dialect=postgresql.dialect()))
        run_ddl = str(CreateTable(ProcurementSourceSyncRun.__table__).compile(dialect=postgresql.dialect()))

        self.assertIn("procurement_source_sync_states", state_ddl)
        self.assertIn("last_sync_missing_critical_fields JSONB", state_ddl)
        self.assertIn("procurement_source_sync_runs", run_ddl)
        self.assertIn("parser_failure_count INTEGER NOT NULL", run_ddl)

    def test_procurement_enrichment_foundation_tables_compile_for_postgres(self) -> None:
        observation_ddl = str(CreateTable(ProcurementLotObservation.__table__).compile(dialect=postgresql.dialect()))
        cache_ddl = str(CreateTable(ProcurementLotDetailCache.__table__).compile(dialect=postgresql.dialect()))
        detail_observation_ddl = str(CreateTable(ProcurementLotDetailObservation.__table__).compile(dialect=postgresql.dialect()))
        http_ddl = str(CreateTable(ProcurementSourceHttpExchange.__table__).compile(dialect=postgresql.dialect()))

        self.assertIn("procurement_lot_observations", observation_ddl)
        self.assertIn("normalized_item JSONB NOT NULL", observation_ddl)
        self.assertIn("procurement_lot_detail_caches", cache_ddl)
        self.assertIn("detail_payload JSONB NOT NULL", cache_ddl)
        self.assertIn("procurement_lot_detail_observations", detail_observation_ddl)
        self.assertIn("procurement_source_http_exchanges", http_ddl)
        self.assertIn("duration_ms INTEGER NOT NULL", http_ddl)

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

    def test_procurement_diagnostics_migration_follows_current_head(self) -> None:
        migration_path = Path("alembic/versions/202605140003_add_procurement_actuality.py")
        spec = importlib.util.spec_from_file_location("procurement_actuality_migration", migration_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        self.assertEqual(module.revision, "202605140003")
        self.assertEqual(module.down_revision, "202605140002")
