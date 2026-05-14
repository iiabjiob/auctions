from __future__ import annotations

from dataclasses import dataclass

from affino_grid_backend import GridColumnDefinition, GridTableDefinition

from app.models.auction import AuctionLotRecord
from app.models.procurement import ProcurementLotRecord
from app.services.auction_grid_edits import WORKSPACE_EDIT_COLUMNS, _workspace_field_for_column
from app.services.auction_grid_state import AUCTION_LOTS_TABLE_ID
from app.services.procurement_calculator import CALCULATOR_INPUT_COLUMNS, calculator_field_for_column
from app.services.procurement_grid_edits import PROCUREMENT_EDIT_COLUMNS, _procurement_field_for_column
from app.services.procurement_grid_state import PROCUREMENT_LOTS_TABLE_ID


@dataclass(frozen=True)
class GridTableRegistryEntry:
    table_id: str
    definition: GridTableDefinition

    def field_for_column(self, column_id: str) -> str:
        definition = self.definition.column(column_id)
        if definition is None:
            raise ValueError(f"Column is not editable: {column_id}")
        return definition.model_attr


def get_grid_table_entry(table_id: str) -> GridTableRegistryEntry:
    if table_id == AUCTION_LOTS_TABLE_ID:
        return auction_lots_grid_table_entry()
    if table_id == PROCUREMENT_LOTS_TABLE_ID:
        return procurement_lots_grid_table_entry()
    raise ValueError(f"Unsupported grid tableId: {table_id}")


def get_grid_table_definition(table_id: str) -> GridTableDefinition:
    return get_grid_table_entry(table_id).definition


def grid_field_for_column(table_id: str, column_id: str) -> str:
    return get_grid_table_entry(table_id).field_for_column(column_id)


def is_supported_grid_table(table_id: str) -> bool:
    return table_id in {AUCTION_LOTS_TABLE_ID, PROCUREMENT_LOTS_TABLE_ID}


def auction_lots_grid_table_entry() -> GridTableRegistryEntry:
    columns = {
        column_id: GridColumnDefinition(
            id=column_id,
            model_attr=field_name,
            editable=True,
            value_type="string",
        )
        for column_id, field_name in WORKSPACE_EDIT_COLUMNS.items()
    }
    return GridTableRegistryEntry(
        table_id=AUCTION_LOTS_TABLE_ID,
        definition=GridTableDefinition(
            table_id=AUCTION_LOTS_TABLE_ID,
            model=AuctionLotRecord,
            row_id_attr="id",
            row_index_attr="id",
            updated_at_attr="updated_at",
            columns=columns,
        ),
    )


def procurement_lots_grid_table_entry() -> GridTableRegistryEntry:
    columns = {
        column_id: GridColumnDefinition(
            id=column_id,
            model_attr=field_name,
            editable=True,
            value_type="string",
        )
        for column_id, field_name in PROCUREMENT_EDIT_COLUMNS.items()
    }
    for column_id, calculator_field in CALCULATOR_INPUT_COLUMNS.items():
        columns[column_id] = GridColumnDefinition(
            id=column_id,
            model_attr=calculator_field,
            editable=True,
            value_type="string",
        )
    return GridTableRegistryEntry(
        table_id=PROCUREMENT_LOTS_TABLE_ID,
        definition=GridTableDefinition(
            table_id=PROCUREMENT_LOTS_TABLE_ID,
            model=ProcurementLotRecord,
            row_id_attr="external_id",
            row_index_attr="id",
            updated_at_attr="updated_at",
            columns=columns,
        ),
    )


def auction_field_for_column(column_id: str) -> str:
    return _workspace_field_for_column(column_id)


def procurement_field_for_column(column_id: str) -> str:
    calculator_field = calculator_field_for_column(column_id)
    if calculator_field is not None:
        return calculator_field
    return _procurement_field_for_column(column_id)
