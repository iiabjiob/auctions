from __future__ import annotations

import unittest
from decimal import Decimal

from sqlalchemy.dialects import postgresql

from app.schemas.auctions import LotDatagridFilters
from app.services.auction_catalog import (
    _apply_record_sort,
    _apply_default_record_sort,
    _build_persisted_lots_statement,
    _grid_filter_predicate,
    _pagination_from_total,
)


class AuctionCatalogSqlTests(unittest.TestCase):
    def test_persisted_statement_filters_before_pagination(self) -> None:
        filters = LotDatagridFilters(
            period="month",
            source="tbankrot",
            status="Идут торги",
            analysis_color="green",
            min_price=Decimal("100000"),
            max_price=Decimal("300000"),
            only_new=True,
            shortlist=True,
            min_rating=70,
        )

        statement = _build_persisted_lots_statement(filters, ("tbankrot",))
        compiled = statement.compile(dialect=postgresql.dialect())
        sql = str(compiled)

        self.assertIn("auction_lot_records.last_seen_at >=", sql)
        self.assertIn("auction_lot_records.source_code =", sql)
        self.assertIn("auction_lot_records.status =", sql)
        self.assertIn("auction_lot_records.is_new IS true", sql)
        self.assertIn("auction_lot_records.rating_score >=", sql)
        self.assertIn("analysis", compiled.params.values())
        self.assertIn("color", compiled.params.values())
        self.assertIn("auction_lot_work_items", sql)
        self.assertNotIn("LIMIT", sql)

    def test_persisted_statement_defaults_to_active_lifecycle_scope(self) -> None:
        statement = _build_persisted_lots_statement(LotDatagridFilters(source="tbankrot"), ("tbankrot",))
        compiled = statement.compile(dialect=postgresql.dialect())
        sql = str(compiled)

        self.assertIn("auction_lot_records.lifecycle_status", sql)
        self.assertIn("active", compiled.params.values())

    def test_persisted_statement_can_include_archived_records_when_requested(self) -> None:
        statement = _build_persisted_lots_statement(
            LotDatagridFilters(source="tbankrot", include_archived=True),
            ("tbankrot",),
        )
        compiled = statement.compile(dialect=postgresql.dialect())
        sql = str(compiled)

        self.assertNotIn("auction_lot_records.lifecycle_status = ", sql)
        self.assertNotIn("active", compiled.params.values())

    def test_default_record_sort_is_sql_level(self) -> None:
        statement = _apply_default_record_sort(
            _build_persisted_lots_statement(LotDatagridFilters(source="tbankrot"), ("tbankrot",))
        )
        compiled = statement.compile(dialect=postgresql.dialect())
        sql = str(compiled)

        self.assertIn("ORDER BY", sql)
        self.assertIn("auction_lot_records.first_seen_at DESC", sql)

    def test_grid_sort_is_applied_at_sql_level(self) -> None:
        statement = _apply_record_sort(
            _build_persisted_lots_statement(LotDatagridFilters(source="tbankrot"), ("tbankrot",)),
            sort_by="ratingScore",
            sort_direction="desc",
        )
        sql = str(statement.compile(dialect=postgresql.dialect()))

        self.assertIn("ORDER BY", sql)
        self.assertIn("auction_lot_records.rating_score DESC", sql)

    def test_grid_sort_model_applies_multiple_sql_sort_columns(self) -> None:
        statement = _apply_record_sort(
            _build_persisted_lots_statement(LotDatagridFilters(source="tbankrot"), ("tbankrot",)),
            sort_model=[
                {"key": "ratingScore", "direction": "desc"},
                {"key": "price", "direction": "asc"},
            ],
        )
        compiled = statement.compile(dialect=postgresql.dialect())
        sql = str(compiled)

        self.assertIn("auction_lot_records.rating_score DESC", sql)
        self.assertIn("current_price_value", compiled.params.values())
        self.assertLess(sql.index("auction_lot_records.rating_score DESC"), sql.index("CAST(nullif"))

    def test_grid_column_filter_is_applied_at_sql_level(self) -> None:
        statement = _build_persisted_lots_statement(
            LotDatagridFilters(source="tbankrot"),
            ("tbankrot",),
            grid_filter={
                "columnFilters": {
                    "lotName": {"kind": "predicate", "operator": "contains", "value": "квартира"},
                    "price": {"kind": "predicate", "operator": "gte", "value": 1_000_000},
                },
                "advancedFilters": {},
            },
        )
        compiled = statement.compile(dialect=postgresql.dialect())
        sql = str(compiled)

        self.assertIn("LIKE", sql)
        self.assertIn("current_price_value", compiled.params.values())
        self.assertIn("%квартира%", compiled.params.values())
        self.assertNotIn("LIMIT", sql)

    def test_grid_text_contains_does_not_fallback_to_datagrid_row_cast(self) -> None:
        statement = _build_persisted_lots_statement(
            LotDatagridFilters(source=None),
            ("tbankrot",),
            grid_filter={
                "advancedExpression": {
                    "kind": "group",
                    "operator": "and",
                    "children": [
                        {"kind": "condition", "key": "lotName", "operator": "contains", "value": "bmw"},
                        {"kind": "condition", "key": "location", "operator": "contains", "value": "москва"},
                    ],
                },
            },
        )
        compiled = statement.compile(dialect=postgresql.dialect())
        sql = str(compiled)

        self.assertIn("auction_lot_records.lot_name", sql)
        self.assertIn("%bmw%", compiled.params.values())
        self.assertNotIn("datagrid_row AS", sql)
        self.assertNotIn("datagrid_row::text", sql.lower())
        self.assertIn("location", compiled.params.values())
        self.assertIn("%москва%", compiled.params.values())

    def test_grid_advanced_expression_applies_category_contains_and_price_gt(self) -> None:
        predicate = _grid_filter_predicate(
            {
                "columnFilters": {},
                "advancedFilters": {},
                "advancedExpression": {
                    "kind": "group",
                    "operator": "and",
                    "children": [
                        {
                            "kind": "condition",
                            "key": "analysisCategory",
                            "operator": "contains",
                            "value": "недвижимость",
                        },
                        {"kind": "condition", "key": "price", "operator": "gt", "value": "1000000"},
                    ],
                },
            }
        )

        self.assertIsNotNone(predicate)
        compiled = predicate.compile(dialect=postgresql.dialect())
        sql = str(compiled)

        self.assertIn(" AND ", sql)
        self.assertIn("LIKE", sql)
        self.assertIn(">", sql)
        self.assertIn("category", compiled.params.values())
        self.assertIn("%недвижимость%", compiled.params.values())
        self.assertIn("current_price_value", compiled.params.values())

    def test_grid_advanced_expression_supports_hyphenated_operator_aliases(self) -> None:
        predicate = _grid_filter_predicate(
            {
                "columnFilters": {},
                "advancedFilters": {},
                "advancedExpression": {
                    "kind": "group",
                    "operator": "and",
                    "children": [
                        {"kind": "condition", "key": "status", "operator": "not-equals", "value": "Отменен"},
                        {"kind": "condition", "key": "applicationDeadline", "operator": "not-empty", "value": ""},
                    ],
                },
            }
        )

        self.assertIsNotNone(predicate)
        compiled = predicate.compile(dialect=postgresql.dialect())
        sql = str(compiled)

        self.assertIn("!=", sql)
        self.assertIn("IS NOT NULL", sql)

    def test_grid_advanced_expression_supports_in_operator(self) -> None:
        predicate = _grid_filter_predicate(
            {
                "columnFilters": {},
                "advancedFilters": {},
                "advancedExpression": {
                    "kind": "condition",
                    "key": "status",
                    "operator": "in",
                    "value": "Идут торги,Прием заявок",
                },
            }
        )

        self.assertIsNotNone(predicate)
        compiled = predicate.compile(dialect=postgresql.dialect())

        self.assertIn(" IN ", str(compiled))
        self.assertIn(["Идут торги", "Прием заявок"], compiled.params.values())

    def test_grid_advanced_expression_text_in_operator_is_case_insensitive(self) -> None:
        predicate = _grid_filter_predicate(
            {
                "advancedExpression": {
                    "kind": "condition",
                    "key": "analysisCategory",
                    "operator": "in",
                    "value": "земля и базы",
                },
            }
        )

        self.assertIsNotNone(predicate)
        compiled = predicate.compile(dialect=postgresql.dialect())

        self.assertIn("lower(", str(compiled))
        self.assertIn(["земля и базы"], compiled.params.values())

    def test_grid_advanced_expression_contains_supports_boolean_columns(self) -> None:
        predicate = _grid_filter_predicate(
            {
                "columnFilters": {},
                "advancedFilters": {},
                "advancedExpression": {
                    "kind": "condition",
                    "key": "isNew",
                    "type": "text",
                    "operator": "contains",
                    "value": "true",
                },
            }
        )

        self.assertIsNotNone(predicate)
        compiled = predicate.compile(dialect=postgresql.dialect())

        self.assertIn("LIKE", str(compiled))
        self.assertIn("%true%", compiled.params.values())

    def test_grid_quick_filter_searches_configured_columns(self) -> None:
        statement = _build_persisted_lots_statement(
            LotDatagridFilters(source=None),
            ("tbankrot",),
            grid_filter={
                "quickFilter": {
                    "query": "bmw москва",
                    "columns": ["lotName", "location", "analysisCategory"],
                    "mode": "tokens",
                },
            },
        )
        compiled = statement.compile(dialect=postgresql.dialect())
        sql = str(compiled)

        self.assertIn("auction_lot_records.lot_name", sql)
        self.assertIn("LIKE", sql)
        self.assertIn("%bmw%", compiled.params.values())
        self.assertIn("%москва%", compiled.params.values())
        self.assertIn("location", compiled.params.values())
        self.assertIn("category", compiled.params.values())
        self.assertNotIn("lower(auction_lot_records.search_text)", sql)

    def test_grid_quick_filter_uses_default_searchable_columns(self) -> None:
        predicate = _grid_filter_predicate({"quickFilter": {"query": "организатор"}})

        self.assertIsNotNone(predicate)
        compiled = predicate.compile(dialect=postgresql.dialect())

        self.assertIn("%организатор%", compiled.params.values())
        self.assertIn("organizer_name", compiled.params.values())

    def test_grid_quick_filter_accepts_organizer_name_alias(self) -> None:
        predicate = _grid_filter_predicate(
            {
                "quickFilter": {
                    "query": "организатор",
                    "columns": ["organizerName"],
                },
            }
        )

        self.assertIsNotNone(predicate)
        compiled = predicate.compile(dialect=postgresql.dialect())

        self.assertIn("%организатор%", compiled.params.values())
        self.assertIn("organizer_name", compiled.params.values())

    def test_short_text_contains_input_is_ignored(self) -> None:
        statement = _build_persisted_lots_statement(
            LotDatagridFilters(source=None),
            ("tbankrot",),
            grid_filter={
                "advancedExpression": {
                    "kind": "condition",
                    "key": "lotName",
                    "operator": "contains",
                    "value": "bm",
                },
            },
        )
        compiled = statement.compile(dialect=postgresql.dialect())
        sql = str(compiled)

        self.assertNotIn("LIKE", sql)
        self.assertNotIn("%bm%", compiled.params.values())

    def test_grid_number_filter_sanitizes_currency_text_before_cast(self) -> None:
        statement = _build_persisted_lots_statement(
            LotDatagridFilters(source="tbankrot"),
            ("tbankrot",),
            grid_filter={
                "columnFilters": {
                    "marketValue": {"kind": "predicate", "operator": "lt", "value": 10_000_000},
                },
                "advancedFilters": {},
            },
        )
        compiled = statement.compile(dialect=postgresql.dialect())
        sql = str(compiled)

        self.assertIn("regexp_replace", sql)
        self.assertIn("[^0-9,.-]+", compiled.params.values())
        self.assertIn("market_value", compiled.params.values())

    def test_grid_number_value_set_filter_sanitizes_currency_text_before_cast(self) -> None:
        predicate = _grid_filter_predicate(
            {
                "columnFilters": {
                    "marketValue": {"kind": "valueSet", "tokens": ["number:3826824.00"]},
                },
                "advancedFilters": {},
            }
        )

        self.assertIsNotNone(predicate)
        compiled = predicate.compile(dialect=postgresql.dialect())
        sql = str(compiled)

        self.assertIn("regexp_replace", sql)
        self.assertIn("[^0-9,.-]+", compiled.params.values())
        self.assertIn("market_value", compiled.params.values())

    def test_grid_number_value_set_filter_uses_single_in_predicate(self) -> None:
        predicate = _grid_filter_predicate(
            {
                "columnFilters": {
                    "marketValue": {
                        "kind": "valueSet",
                        "tokens": ["number:1000000", "number:2000000", "number:3000000"],
                    },
                },
                "advancedFilters": {},
            }
        )

        self.assertIsNotNone(predicate)
        compiled = predicate.compile(dialect=postgresql.dialect())
        sql = str(compiled)

        self.assertIn(" IN ", sql)
        self.assertEqual(sql.count("regexp_replace("), 1)

    def test_grid_roi_filter_uses_persisted_row_value(self) -> None:
        predicate = _grid_filter_predicate(
            {
                "columnFilters": {
                    "roiValue": {"kind": "predicate", "operator": "gte", "value": "0.25"},
                },
                "advancedFilters": {},
            }
        )

        self.assertIsNotNone(predicate)
        compiled = predicate.compile(dialect=postgresql.dialect())
        sql = str(compiled)

        self.assertNotIn("/", sql)
        self.assertNotIn("market_value", compiled.params.values())
        self.assertNotIn("current_price_value", compiled.params.values())
        self.assertNotIn("platform_fee", compiled.params.values())
        self.assertIn("roi", compiled.params.values())

    def test_grid_current_price_filter_accepts_api_aliases(self) -> None:
        for key in ("price", "currentPrice", "currentPriceValue", "current_price_value"):
            with self.subTest(key=key):
                predicate = _grid_filter_predicate(
                    {
                        "columnFilters": {
                            key: {"kind": "predicate", "operator": "gte", "value": "1000000"},
                        },
                        "advancedFilters": {},
                    }
                )

                self.assertIsNotNone(predicate)
                compiled = predicate.compile(dialect=postgresql.dialect())

                self.assertIn(">=", str(compiled))
                self.assertIn("current_price_value", compiled.params.values())

    def test_grid_visible_columns_have_filter_expressions(self) -> None:
        text_columns = (
            "analysisLabel",
            "analysisCategory",
            "sourceTitle",
            "auctionNumber",
            "publicationDate",
            "lotNumber",
            "lotName",
            "location",
            "status",
            "organizer",
            "applicationDeadline",
            "auctionDate",
            "lastSeenAt",
            "exclusionReason",
        )
        number_columns = (
            "ratingScore",
            "initialPrice",
            "price",
            "minimumPrice",
            "marketValue",
            "platformFee",
            "deliveryCost",
            "dismantlingCost",
            "repairCost",
            "storageCost",
            "legalCost",
            "otherCosts",
            "targetProfit",
            "totalExpenses",
            "fullEntryCost",
            "potentialProfit",
            "roiValue",
            "marketDiscount",
            "formulaMaxPurchasePrice",
        )
        boolean_columns = ("isNew", "excludeFromAnalysis")

        for key in text_columns:
            with self.subTest(key=key):
                predicate = _grid_filter_predicate(
                    {"columnFilters": {key: {"kind": "predicate", "operator": "not-empty", "value": ""}}}
                )
                self.assertIsNotNone(predicate)

        for key in number_columns:
            with self.subTest(key=key):
                predicate = _grid_filter_predicate(
                    {"columnFilters": {key: {"kind": "predicate", "operator": "gte", "value": "1"}}}
                )
                self.assertIsNotNone(predicate)

        for key in boolean_columns:
            with self.subTest(key=key):
                predicate = _grid_filter_predicate(
                    {"columnFilters": {key: {"kind": "predicate", "operator": "equals", "value": True}}}
                )
                self.assertIsNotNone(predicate)

    def test_grid_filter_accepts_api_aliases_for_display_columns(self) -> None:
        cases = (
            ("source_title", "not-empty", "", "source_title"),
            ("auction_number", "not-empty", "", None),
            ("publication_date", "not-empty", "", "publication_date"),
            ("lot_number", "not-empty", "", None),
            ("lot_name", "not-empty", "", None),
            ("location_region", "not-empty", "", "location_region"),
            ("organizer_name", "not-empty", "", "organizer_name"),
            ("application_deadline", "not-empty", "", "application_deadline"),
            ("auction_date", "not-empty", "", "auction_date"),
            ("last_seen_at", "not-empty", "", None),
            ("initial_price_value", "gte", "1", "initial_price_value"),
            ("current_price_value", "gte", "1", "current_price_value"),
            ("minimum_price_value", "gte", "1", "minimum_price_value"),
            ("market_value", "gte", "1", "market_value"),
            ("platform_fee", "gte", "1", "platform_fee"),
            ("delivery_cost", "gte", "1", "delivery_cost"),
            ("dismantling_cost", "gte", "1", "dismantling_cost"),
            ("repair_cost", "gte", "1", "repair_cost"),
            ("storage_cost", "gte", "1", "storage_cost"),
            ("legal_cost", "gte", "1", "legal_cost"),
            ("other_costs", "gte", "1", "other_costs"),
            ("target_profit", "gte", "1", "target_profit"),
            ("total_expenses", "gte", "1", "total_expenses"),
            ("full_entry_cost", "gte", "1", "full_entry_cost"),
            ("potential_profit", "gte", "1", "potential_profit"),
            ("roi", "gte", "1", "roi"),
            ("roi_value", "gte", "1", "roi"),
            ("market_discount", "gte", "1", "market_discount"),
            ("formula_max_purchase_price", "gte", "1", "formula_max_purchase_price"),
            ("is_new", "equals", True, None),
            ("exclude_from_analysis", "equals", True, "exclude_from_analysis"),
            ("work_decision_status", "not-empty", "", None),
        )

        for key, operator, value, expected_param in cases:
            with self.subTest(key=key):
                predicate = _grid_filter_predicate(
                    {"columnFilters": {key: {"kind": "predicate", "operator": operator, "value": value}}}
                )
                self.assertIsNotNone(predicate)
                if expected_param is not None:
                    compiled = predicate.compile(dialect=postgresql.dialect())
                    self.assertIn(expected_param, compiled.params.values())

    def test_grid_roi_sort_uses_persisted_row_value(self) -> None:
        statement = _apply_record_sort(
            _build_persisted_lots_statement(LotDatagridFilters(source="tbankrot"), ("tbankrot",)),
            sort_model=[{"key": "roiValue", "direction": "desc"}],
        )
        compiled = statement.compile(dialect=postgresql.dialect())
        sql = str(compiled)

        self.assertIn("ORDER BY", sql)
        self.assertNotIn("/", sql)
        self.assertNotIn("market_value", compiled.params.values())
        self.assertNotIn("current_price_value", compiled.params.values())
        self.assertIn("roi", compiled.params.values())

    def test_grid_value_set_string_filter_is_case_insensitive(self) -> None:
        predicate = _grid_filter_predicate(
            {
                "columnFilters": {
                    "location": {"kind": "valueSet", "tokens": ["string:москва"]},
                },
                "advancedFilters": {},
            }
        )
        self.assertIsNotNone(predicate)
        compiled = predicate.compile(dialect=postgresql.dialect())
        sql = str(compiled)

        self.assertIn("lower", sql.lower())
        self.assertIn("location", compiled.params.values())
        self.assertIn(["москва"], compiled.params.values())

    def test_grid_advanced_expression_supports_or_groups(self) -> None:
        predicate = _grid_filter_predicate(
            {
                "columnFilters": {},
                "advancedFilters": {},
                "advancedExpression": {
                    "kind": "group",
                    "operator": "or",
                    "children": [
                        {"kind": "condition", "key": "status", "operator": "equals", "value": "Идут торги"},
                        {"kind": "condition", "key": "ratingScore", "operator": "gte", "value": 90},
                    ],
                },
            }
        )
        self.assertIsNotNone(predicate)
        compiled = predicate.compile(dialect=postgresql.dialect())
        sql = str(compiled)

        self.assertIn(" OR ", sql)
        self.assertIn("auction_lot_records.status", sql)
        self.assertIn("auction_lot_records.rating_score", sql)

    def test_grid_advanced_expression_ignores_invalid_number_value(self) -> None:
        predicate = _grid_filter_predicate(
            {
                "columnFilters": {},
                "advancedFilters": {},
                "advancedExpression": {
                    "kind": "group",
                    "operator": "and",
                    "children": [
                        {"kind": "condition", "key": "ratingScore", "operator": "gte", "value": "not-a-number"},
                    ],
                },
            }
        )

        self.assertIsNone(predicate)

    def test_pagination_uses_total_from_filtered_dataset(self) -> None:
        pagination = _pagination_from_total(25_001, page=999, page_size=10_000)

        self.assertEqual(pagination.total, 25_001)
        self.assertEqual(pagination.total_pages, 3)
        self.assertEqual(pagination.page, 3)

    def test_pagination_can_be_derived_from_offset(self) -> None:
        pagination = _pagination_from_total(25_001, page=1, page_size=100, offset=1_200)

        self.assertEqual(pagination.total, 25_001)
        self.assertEqual(pagination.total_pages, 251)
        self.assertEqual(pagination.page, 13)


if __name__ == "__main__":
    unittest.main()
