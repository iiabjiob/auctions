from __future__ import annotations

import unittest

from app.models.auction import AuctionLotRecord
from app.models.procurement import ProcurementLotRecord
from app.services.auction_grid_state import AUCTION_LOTS_TABLE_ID
from app.services.grid_table_registry import (
    auction_field_for_column,
    get_grid_table_definition,
    grid_field_for_column,
    is_supported_grid_table,
    procurement_field_for_column,
)
from app.services.procurement_grid_state import PROCUREMENT_LOTS_TABLE_ID


class GridTableRegistryTests(unittest.TestCase):
    def test_auction_table_definition_contains_workspace_columns(self) -> None:
        definition = get_grid_table_definition(AUCTION_LOTS_TABLE_ID)

        self.assertEqual(definition.table_id, AUCTION_LOTS_TABLE_ID)
        self.assertIs(definition.model, AuctionLotRecord)
        self.assertEqual(definition.column("comment").model_attr, "comment")
        self.assertEqual(definition.column("maxPurchasePrice").model_attr, "max_purchase_price")

    def test_procurement_table_definition_contains_record_and_calculator_columns(self) -> None:
        definition = get_grid_table_definition(PROCUREMENT_LOTS_TABLE_ID)

        self.assertEqual(definition.table_id, PROCUREMENT_LOTS_TABLE_ID)
        self.assertIs(definition.model, ProcurementLotRecord)
        self.assertEqual(definition.column("workflowStatus").model_attr, "workflow_status")
        self.assertEqual(definition.column("fabricPrice").model_attr, "fabric_price")

    def test_field_mapping_helpers_are_table_specific(self) -> None:
        self.assertEqual(auction_field_for_column("decisionStatus"), "decision_status")
        self.assertEqual(procurement_field_for_column("workflowStatus"), "workflow_status")
        self.assertEqual(procurement_field_for_column("fabricPrice"), "fabric_price")
        self.assertEqual(grid_field_for_column(AUCTION_LOTS_TABLE_ID, "marketValue"), "market_value")

    def test_supported_tables_are_explicit(self) -> None:
        self.assertTrue(is_supported_grid_table(AUCTION_LOTS_TABLE_ID))
        self.assertTrue(is_supported_grid_table(PROCUREMENT_LOTS_TABLE_ID))
        self.assertFalse(is_supported_grid_table("unknown"))

