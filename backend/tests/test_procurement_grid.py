from __future__ import annotations

import unittest
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy.dialects import postgresql

from app.models.procurement import ProcurementLotRecord
from app.schemas.procurement_grid import (
    ProcurementLotsGridPullRequest,
    ProcurementLotsGridPullResponse,
    ProcurementLotsGridSummary,
)
from app.services.procurement_grid import (
    _apply_record_sort,
    _build_procurement_lots_statement,
    _grid_filter_predicate,
    _merge_query_options_into_filter_model,
    _normalize_sort_model,
    build_procurement_grid_row,
    pull_procurement_lots_grid,
)
from app.services.procurement_grid_state import PROCUREMENT_LOTS_TABLE_ID, procurement_lot_grid_row_id


class ProcurementGridSchemaTests(unittest.TestCase):
    def test_pull_request_accepts_flat_and_nested_range_fields(self) -> None:
        flat = ProcurementLotsGridPullRequest.model_validate(
            {
                "startRow": 10,
                "endRow": 20,
                "sortModel": [{"colId": "score", "sort": "desc"}],
                "workflowStatus": "new",
                "minScore": 75,
            }
        )
        nested = ProcurementLotsGridPullRequest.model_validate({"range": {"startRow": 0, "endRow": 50}})

        self.assertEqual(flat.resolved_start_row, 10)
        self.assertEqual(flat.resolved_end_row, 20)
        self.assertEqual(flat.workflow_status, "new")
        self.assertEqual(flat.min_score, 75)
        self.assertEqual(nested.resolved_start_row, 0)
        self.assertEqual(nested.resolved_end_row, 50)

    def test_pull_response_uses_dataset_version_alias(self) -> None:
        payload = ProcurementLotsGridPullResponse(
            rows=[],
            total=0,
            dataset_version=3,
            summary=ProcurementLotsGridSummary(total=0, new_count=1, relevant_count=2, high_score_count=3),
        ).model_dump(by_alias=True)

        self.assertEqual(payload["datasetVersion"], 3)
        self.assertEqual(payload["summary"]["newCount"], 1)
        self.assertEqual(payload["summary"]["relevantCount"], 2)
        self.assertEqual(payload["summary"]["highScoreCount"], 3)

    def test_procurement_grid_row_id_is_separate_table_contract(self) -> None:
        record = ProcurementLotRecord(source_code="zakupki", external_id="123", registry_number="123", content_hash="h", normalized_item={}, raw_item={})

        self.assertEqual(PROCUREMENT_LOTS_TABLE_ID, "procurement-lots")
        self.assertEqual(procurement_lot_grid_row_id(record), "zakupki:123")


class ProcurementGridSqlTests(unittest.TestCase):
    def test_query_options_are_merged_into_advanced_expression(self) -> None:
        request = ProcurementLotsGridPullRequest.model_validate(
            {
                "startRow": 0,
                "endRow": 10,
                "source": "zakupki",
                "law": "44-ФЗ",
                "workflowStatus": "new",
                "category": "Спецодежда",
                "minPrice": "300000",
                "maxPrice": "30000000",
                "minScore": 75,
                "onlyNew": True,
            }
        )

        filter_model = _merge_query_options_into_filter_model(None, request)

        expression = filter_model["advancedExpression"]
        self.assertEqual(expression["kind"], "group")
        self.assertEqual(
            {(condition["key"], condition["operator"]) for condition in expression["children"]},
            {
                ("source", "equals"),
                ("law", "equals"),
                ("workflowStatus", "equals"),
                ("category", "equals"),
                ("initialPrice", "gte"),
                ("initialPrice", "lte"),
                ("score", "gte"),
                ("isNew", "equals"),
            },
        )

    def test_grid_filter_predicate_compiles_for_text_and_number_filters(self) -> None:
        predicate = _grid_filter_predicate(
            {
                "advancedExpression": {
                    "kind": "group",
                    "operator": "and",
                    "children": [
                        {"kind": "condition", "key": "title", "operator": "contains", "value": "спецодежда"},
                        {"kind": "condition", "key": "initialPrice", "operator": "gte", "value": "300000"},
                    ],
                }
            }
        )

        self.assertIsNotNone(predicate)
        compiled = predicate.compile(dialect=postgresql.dialect())
        sql = str(compiled)

        self.assertIn("LIKE", sql)
        self.assertIn(">=", sql)
        self.assertIn("%спецодежда%", compiled.params.values())

    def test_procurement_statement_filters_before_pagination(self) -> None:
        statement = _build_procurement_lots_statement(
            grid_filter={"quickFilter": {"query": "медицинская одежда", "columns": ["title", "customerName"]}}
        )
        compiled = statement.compile(dialect=postgresql.dialect())
        sql = str(compiled)

        self.assertIn("procurement_lot_records", sql)
        self.assertIn("procurement_lot_records.lifecycle_status", sql)
        self.assertIn("LIKE", sql)
        self.assertNotIn("LIMIT", sql)

    def test_grid_sort_is_applied_at_sql_level(self) -> None:
        statement = _apply_record_sort(
            _build_procurement_lots_statement(),
            sort_model=[{"key": "score", "direction": "desc"}, {"key": "applicationDeadline", "direction": "asc"}],
        )
        sql = str(statement.compile(dialect=postgresql.dialect()))

        self.assertIn("ORDER BY", sql)
        self.assertIn("procurement_lot_records.attractiveness_score DESC", sql)
        self.assertIn("procurement_lot_records.application_deadline_at ASC", sql)

    def test_sort_model_normalizes_affino_shapes(self) -> None:
        self.assertEqual(
            _normalize_sort_model([{"colId": "score", "sort": "desc"}, {"key": "title", "direction": "asc"}]),
            [{"key": "score", "direction": "desc"}, {"key": "title", "direction": "asc"}],
        )


class ProcurementGridRowTests(unittest.TestCase):
    def test_build_procurement_grid_row_shapes_values_for_frontend(self) -> None:
        record = ProcurementLotRecord(
            id=7,
            source_code="zakupki",
            external_id="123",
            registry_number="123",
            law="44-ФЗ",
            title="Поставка спецодежды",
            customer_name="Заказчик",
            customer_inn="7700000000",
            initial_price_value=Decimal("1200000.50"),
            publication_at=datetime(2026, 5, 13, tzinfo=UTC),
            application_deadline_at=datetime(2026, 5, 20, 9, tzinfo=UTC),
            category="Спецодежда",
            matched_keywords=["спецодежда"],
            excluded_keywords=[],
            filter_reason="matched_category:Спецодежда",
            attractiveness_score=83,
            attractiveness_level="high",
            attractiveness_reasons=["активный этап"],
            workflow_status="new",
            content_hash="h",
            normalized_item={},
            raw_item={},
        )

        row = build_procurement_grid_row(record)

        self.assertEqual(row["id"], "zakupki:123")
        self.assertEqual(row["recordId"], 7)
        self.assertEqual(row["registryNumber"], "123")
        self.assertEqual(row["customerInn"], "7700000000")
        self.assertEqual(row["initialPrice"], 1200000.50)
        self.assertEqual(row["score"], 83)
        self.assertEqual(row["workflowStatus"], "new")
        self.assertEqual(row["matchedKeywords"], ["спецодежда"])
        self.assertEqual(row["lifecycleStatus"], "active")


class ProcurementGridPullServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_pull_response_indexes_are_viewport_positions(self) -> None:
        request = ProcurementLotsGridPullRequest.model_validate({"startRow": 10, "endRow": 12})
        records = [SimpleNamespace(source_code="zakupki", external_id="101"), SimpleNamespace(source_code="zakupki", external_id="204")]
        rows = [{"id": "zakupki:101"}, {"id": "zakupki:204"}]

        with (
            patch("app.services.procurement_grid.read_procurement_grid_dataset_version", AsyncMock(return_value=7)),
            patch("app.services.procurement_grid.pull_procurement_lots_for_grid", AsyncMock(return_value=(list(zip(records, rows)), 100))),
            patch("app.services.procurement_grid.summarize_procurement_lots_for_grid", AsyncMock(return_value=ProcurementLotsGridSummary(total=100, new_count=4))),
        ):
            response = await pull_procurement_lots_grid(AsyncMock(), request)

        self.assertEqual([row.index for row in response.rows], [10, 11])
        self.assertEqual([row.id for row in response.rows], ["zakupki:101", "zakupki:204"])
        self.assertEqual(response.total, 100)
        self.assertEqual(response.dataset_version, 7)
        self.assertEqual(response.summary.new_count, 4)
