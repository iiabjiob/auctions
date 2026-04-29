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
            q="квартира 50%",
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
        self.assertIn("LIKE", sql)
        self.assertNotIn("LIMIT", sql)
        self.assertIn("%квартира 50\\%%", compiled.params.values())

    def test_default_record_sort_is_sql_level(self) -> None:
        statement = _apply_default_record_sort(
            _build_persisted_lots_statement(LotDatagridFilters(source="tbankrot"), ("tbankrot",))
        )
        compiled = statement.compile(dialect=postgresql.dialect())
        sql = str(compiled)

        self.assertIn("ORDER BY", sql)
        self.assertIn("source_position", compiled.params.values())

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
