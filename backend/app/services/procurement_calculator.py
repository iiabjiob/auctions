from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from app.models.procurement import ProcurementLotRecord


SCENARIOS = ("optimistic", "realistic", "cautious")
DEFAULT_DECISION_SCENARIO = "cautious"
DEFAULT_VAT_RATE = Decimal("0.22")
DEFAULT_PROFIT_TAX_RATE = Decimal("0.25")
MONEY_QUANT = Decimal("0.01")
RATIO_QUANT = Decimal("0.000001")
CALCULATOR_INPUT_COLUMNS = {
    "productType": "product_type",
    "fabricType": "fabric_type",
    "fabricPrice": "fabric_price",
    "fabricConsumptionPerUnit": "fabric_consumption_per_unit",
    "accessoriesCost": "accessories_cost",
    "sewingCost": "sewing_cost",
    "extraOperationsCost": "extra_operations_cost",
    "logisticsCost": "logistics_cost",
    "packagingCost": "packaging_cost",
    "defectReservePercent": "defect_reserve_percent",
    "adminFotCost": "admin_fot_cost",
    "vatMode": "vat_mode",
    "vatRate": "vat_rate",
    "profitTaxRate": "profit_tax_rate",
}
CALCULATOR_INPUT_COLUMNS.update({field_name: field_name for field_name in set(CALCULATOR_INPUT_COLUMNS.values())})
DECIMAL_INPUT_FIELDS = {
    "admin_fot_cost",
    "accessories_cost",
    "defect_reserve_percent",
    "extra_operations_cost",
    "fabric_consumption_per_unit",
    "fabric_price",
    "logistics_cost",
    "packaging_cost",
    "profit_tax_rate",
    "sewing_cost",
    "vat_rate",
}
TEXT_INPUT_FIELDS = {"fabric_type", "product_type", "vat_mode"}
VAT_MODES = {"included", "excluded", "none"}


def recalculate_procurement_lot(record: ProcurementLotRecord) -> dict[str, Any]:
    result = calculate_procurement_lot(record)
    record.calculator_scenarios = result

    realistic = result.get("realistic") or {}
    cautious = result.get(DEFAULT_DECISION_SCENARIO) or {}
    record.cost_realistic = _decimal_or_none(realistic.get("fullCost"))
    record.cost_cautious = _decimal_or_none(cautious.get("fullCost"))
    record.net_profit = _decimal_or_none(cautious.get("netProfit"))
    record.profitability = _decimal_or_none(cautious.get("profitability"))
    record.roi = _decimal_or_none(cautious.get("roi"))
    record.cash_gap_peak = _decimal_or_none(cautious.get("cashGapPeak"))
    return result


def calculate_procurement_lot(record: ProcurementLotRecord) -> dict[str, Any]:
    base_inputs = dict(record.calculator_inputs or {})
    scenario_overrides = base_inputs.get("scenarios") if isinstance(base_inputs.get("scenarios"), dict) else {}
    return {
        scenario: calculate_procurement_scenario(
            record,
            _merge_scenario_inputs(base_inputs, scenario_overrides.get(scenario)),
            scenario=scenario,
        )
        for scenario in SCENARIOS
    }


def calculate_procurement_scenario(
    record: ProcurementLotRecord,
    inputs: dict[str, Any],
    *,
    scenario: str = DEFAULT_DECISION_SCENARIO,
) -> dict[str, Any]:
    quantity = _decimal_or_none(record.quantity) or _input_decimal(inputs, "quantity")
    unit_nmck = _decimal_or_none(record.unit_nmck) or _input_decimal(inputs, "unit_nmck")
    total_revenue = _decimal_or_none(record.initial_price_value)
    if quantity is not None and unit_nmck is not None:
        total_revenue = unit_nmck * quantity
    elif total_revenue is not None and quantity is not None and unit_nmck is None and quantity != 0:
        unit_nmck = total_revenue / quantity

    missing = [
        key
        for key, value in (
            ("quantity", quantity),
            ("unitNmck", unit_nmck),
            ("fabricPrice", _input_decimal(inputs, "fabric_price")),
            ("fabricConsumptionPerUnit", _input_decimal(inputs, "fabric_consumption_per_unit")),
        )
        if value is None
    ]
    if total_revenue is None and "unitNmck" not in missing:
        missing.append("revenue")
    if missing:
        return _empty_scenario(scenario, missing)

    fabric_price = _input_decimal(inputs, "fabric_price") or Decimal("0")
    fabric_consumption = _input_decimal(inputs, "fabric_consumption_per_unit") or Decimal("0")
    accessories_cost = _input_decimal(inputs, "accessories_cost") or Decimal("0")
    sewing_cost = _input_decimal(inputs, "sewing_cost") or Decimal("0")
    extra_operations_cost = _input_decimal(inputs, "extra_operations_cost") or Decimal("0")
    logistics_cost = _input_decimal(inputs, "logistics_cost") or Decimal("0")
    packaging_cost = _input_decimal(inputs, "packaging_cost") or Decimal("0")
    defect_reserve_rate = _percent_to_rate(_input_decimal(inputs, "defect_reserve_percent"))
    admin_fot_cost = _input_decimal(inputs, "admin_fot_cost") or Decimal("0")
    vat_rate = _input_decimal(inputs, "vat_rate") or DEFAULT_VAT_RATE
    profit_tax_rate = _input_decimal(inputs, "profit_tax_rate") or DEFAULT_PROFIT_TAX_RATE
    vat_mode = str(inputs.get("vat_mode") or "included").strip().lower()
    if vat_mode not in VAT_MODES:
        vat_mode = "included"

    fabric_cost_per_unit = fabric_price * fabric_consumption
    direct_unit_cost = (
        fabric_cost_per_unit
        + accessories_cost
        + sewing_cost
        + extra_operations_cost
        + logistics_cost
        + packaging_cost
    )
    unit_cost = direct_unit_cost * (Decimal("1") + defect_reserve_rate)
    production_cost = unit_cost * (quantity or Decimal("0"))
    full_cost = production_cost + admin_fot_cost
    revenue_without_vat = _revenue_without_vat(total_revenue or Decimal("0"), vat_mode=vat_mode, vat_rate=vat_rate)
    output_vat = Decimal("0") if vat_mode == "none" else revenue_without_vat * vat_rate
    input_vat = Decimal("0") if vat_mode == "none" else full_cost * vat_rate
    vat_payable = max(output_vat - input_vat, Decimal("0"))
    gross_profit = revenue_without_vat - full_cost
    profit_tax = max(gross_profit, Decimal("0")) * profit_tax_rate
    net_profit = gross_profit - profit_tax
    profitability = _safe_div(net_profit, revenue_without_vat)
    roi = _safe_div(net_profit, full_cost)
    prepayment = (total_revenue or Decimal("0")) * _percent_to_rate(record.prepayment_percent)
    cash_gap_peak = (
        full_cost
        + (record.bid_security_amount or Decimal("0"))
        + (record.contract_security_amount or Decimal("0"))
        - prepayment
    )

    return {
        "scenario": scenario,
        "complete": True,
        "missingInputs": [],
        "vatMode": vat_mode,
        "vatRate": _json_decimal(vat_rate, RATIO_QUANT),
        "profitTaxRate": _json_decimal(profit_tax_rate, RATIO_QUANT),
        "fabricCostPerUnit": _json_decimal(fabric_cost_per_unit),
        "unitCost": _json_decimal(unit_cost),
        "productionCost": _json_decimal(production_cost),
        "fullCost": _json_decimal(full_cost),
        "revenueWithoutVat": _json_decimal(revenue_without_vat),
        "grossProfit": _json_decimal(gross_profit),
        "vatPayable": _json_decimal(vat_payable),
        "profitTax": _json_decimal(profit_tax),
        "netProfit": _json_decimal(net_profit),
        "profitability": _json_decimal(profitability, RATIO_QUANT),
        "roi": _json_decimal(roi, RATIO_QUANT),
        "cashGapPeak": _json_decimal(cash_gap_peak),
    }


def calculator_field_for_column(column_id: str) -> str | None:
    return CALCULATOR_INPUT_COLUMNS.get(column_id)


def coerce_calculator_input_value(field_name: str, value: Any) -> Any:
    if field_name in DECIMAL_INPUT_FIELDS:
        coerced = _coerce_decimal(value, field_name)
        return _json_decimal(coerced, RATIO_QUANT if field_name.endswith("_rate") else MONEY_QUANT)
    if field_name in TEXT_INPUT_FIELDS:
        coerced = _coerce_nullable_text(value, field_name)
        if field_name == "vat_mode" and coerced is not None and coerced not in VAT_MODES:
            raise ValueError(f"vat_mode must be one of: {', '.join(sorted(VAT_MODES))}")
        return coerced
    raise ValueError(f"Calculator field is not editable: {field_name}")


def _merge_scenario_inputs(base_inputs: dict[str, Any], override: Any) -> dict[str, Any]:
    merged = {key: value for key, value in base_inputs.items() if key != "scenarios"}
    if isinstance(override, dict):
        merged.update(override)
    return merged


def _empty_scenario(scenario: str, missing: list[str]) -> dict[str, Any]:
    return {"scenario": scenario, "complete": False, "missingInputs": missing}


def _input_decimal(inputs: dict[str, Any], field_name: str) -> Decimal | None:
    return _decimal_or_none(inputs.get(field_name))


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _coerce_decimal(value: Any, field_name: str) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip().replace(" ", "").replace(",", ".")
        if not normalized:
            return None
    elif isinstance(value, Decimal):
        normalized = str(value)
    elif isinstance(value, bool):
        raise ValueError(f"{field_name} must be a number")
    elif isinstance(value, int | float):
        normalized = str(value)
    else:
        raise ValueError(f"{field_name} must be a number")
    try:
        return Decimal(normalized)
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"{field_name} must be a number") from error


def _coerce_nullable_text(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict | list):
        raise ValueError(f"{field_name} must be text")
    normalized = str(value).strip()
    return normalized or None


def _percent_to_rate(value: Any) -> Decimal:
    decimal_value = _decimal_or_none(value)
    if decimal_value is None:
        return Decimal("0")
    if abs(decimal_value) > Decimal("1"):
        return decimal_value / Decimal("100")
    return decimal_value


def _revenue_without_vat(total_revenue: Decimal, *, vat_mode: str, vat_rate: Decimal) -> Decimal:
    if vat_mode == "included":
        return total_revenue / (Decimal("1") + vat_rate)
    return total_revenue


def _safe_div(numerator: Decimal, denominator: Decimal | None) -> Decimal | None:
    if denominator is None or denominator == 0:
        return None
    return numerator / denominator


def _json_decimal(value: Decimal | None, quant: Decimal = MONEY_QUANT) -> str | None:
    if value is None:
        return None
    return str(value.quantize(quant, rounding=ROUND_HALF_UP))
