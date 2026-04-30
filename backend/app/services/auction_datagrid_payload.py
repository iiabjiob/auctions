from __future__ import annotations

from decimal import Decimal

from app.schemas.auctions import LotDatagridRow
from app.services.auction_values import parse_price


DECIMAL_ROW_FIELDS = {
    "initial_price_value",
    "current_price_value",
    "minimum_price_value",
    "market_value",
    "platform_fee",
    "delivery_cost",
    "dismantling_cost",
    "repair_cost",
    "storage_cost",
    "legal_cost",
    "other_costs",
    "target_profit",
    "total_expenses",
    "full_entry_cost",
    "potential_profit",
    "roi",
    "market_discount",
    "formula_max_purchase_price",
}


def validate_datagrid_row_payload(payload: dict) -> LotDatagridRow:
    return LotDatagridRow.model_validate(sanitize_datagrid_row_payload(payload))


def sanitize_datagrid_row_payload(payload: dict) -> dict:
    row = dict(payload or {})
    for field in DECIMAL_ROW_FIELDS:
        if field in row:
            row[field] = _sanitize_decimal_row_value(row[field])
    if row.get("exclude_from_analysis") is None:
        row["exclude_from_analysis"] = False
    return row


def _sanitize_decimal_row_value(value: object) -> object:
    if value is None or isinstance(value, Decimal):
        return value
    if isinstance(value, int | float):
        return str(value)
    if not isinstance(value, str):
        return value
    normalized = value.strip()
    if not normalized:
        return None
    if any(char.isdigit() for char in normalized):
        parsed = parse_price(normalized)
        return str(parsed) if parsed is not None else value
    return value
