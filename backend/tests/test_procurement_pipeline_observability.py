from __future__ import annotations

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace

from app.models.procurement import ProcurementLotRecord, ProcurementSourceSyncState
from app.services.procurement_pipeline_observability import (
    build_procurement_pipeline_counters_statement,
    build_procurement_source_sync_status,
    get_procurement_pipeline_health,
)
from app.services.procurement_scoring import PROCUREMENT_SCORING_VERSION


class FakeExecuteResult:
    def __init__(self, row: object) -> None:
        self._row = row

    def one(self) -> object:
        return self._row

    def scalars(self) -> "FakeScalars":
        return FakeScalars([self._row] if self._row is not None else [])


class FakeScalars:
    def __init__(self, values: list[object]) -> None:
        self._values = values

    def all(self) -> list[object]:
        return self._values


class FakeSession:
    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, statement: object) -> FakeExecuteResult:
        del statement
        self.calls += 1
        if self.calls == 1:
            return FakeExecuteResult(
                SimpleNamespace(
                    total_lots=10,
                    priority_lots=3,
                    decision_pending_lots=2,
                    missing_documents=1,
                    missing_critical_fields=4,
                    scoring_stale_or_incomplete=5,
                    scored_current=5,
                )
            )
        return FakeExecuteResult(
            ProcurementSourceSyncState(
                source_code="zakupki",
                last_sync_started_at=datetime(2026, 5, 13, 10, tzinfo=UTC),
                last_sync_completed_at=datetime(2026, 5, 13, 10, 3, tzinfo=UTC),
                last_successful_sync_at=datetime(2026, 5, 13, 10, 3, tzinfo=UTC),
                last_sync_result="success",
                last_sync_fetched=10,
                last_sync_created=4,
                last_sync_updated=1,
                last_sync_unchanged=5,
                last_sync_status_changed=1,
                last_sync_parser_failures=0,
                last_sync_missing_critical_fields={"title": 2},
                parser_version="zakupki-eis-v1",
            )
        )


class ProcurementPipelineObservabilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_pipeline_health_maps_counters_and_source_statuses(self) -> None:
        response = await get_procurement_pipeline_health(FakeSession())

        self.assertEqual(response.counters.total_lots, 10)
        self.assertEqual(response.counters.priority_lots, 3)
        zakupki = next(source for source in response.sources if source.code == "zakupki")
        self.assertEqual(zakupki.last_sync_result, "success")
        self.assertEqual(zakupki.last_sync_missing_critical_fields, {"title": 2})
        self.assertEqual(zakupki.parser_version, "zakupki-eis-v1")
        disabled = next(source for source in response.sources if source.code == "sberbank_ast")
        self.assertFalse(disabled.enabled)

    def test_source_status_includes_failure_diagnostics(self) -> None:
        status = build_procurement_source_sync_status(
            SimpleNamespace(code="zakupki", title="ЕИС", website="https://zakupki.gov.ru", enabled=True),
            sync_state=ProcurementSourceSyncState(
                source_code="zakupki",
                last_sync_result="failed",
                last_sync_error="timeout",
                last_sync_error_code="TimeoutError",
                last_sync_parser_failures=3,
                last_sync_missing_critical_fields={"registry_number": 1},
            ),
        )

        self.assertEqual(status.last_sync_result, "failed")
        self.assertEqual(status.last_sync_error, "timeout")
        self.assertEqual(status.last_sync_error_code, "TimeoutError")
        self.assertEqual(status.last_sync_parser_failures, 3)
        self.assertEqual(status.last_sync_missing_critical_fields, {"registry_number": 1})

    def test_pipeline_counter_statement_contains_expected_filters(self) -> None:
        statement = build_procurement_pipeline_counters_statement()
        sql = str(statement.compile(compile_kwargs={"literal_binds": True}))

        self.assertIn("procurement_lot_records.attractiveness_score >= 75", sql)
        self.assertIn("procurement_lot_records.workflow_status = 'decision'", sql)
        self.assertIn(f"procurement_lot_records.scoring_version = '{PROCUREMENT_SCORING_VERSION}'", sql)
        self.assertIn("procurement_lot_records.application_deadline_at IS NULL", sql)


if __name__ == "__main__":
    unittest.main()
