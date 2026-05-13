from __future__ import annotations

import unittest
from decimal import Decimal

from app.models.procurement import ProcurementLotRecord
from app.services.procurement_calculator import calculate_procurement_lot, recalculate_procurement_lot


def make_record() -> ProcurementLotRecord:
    return ProcurementLotRecord(
        source_code="zakupki",
        external_id="123",
        registry_number="0123456789",
        content_hash="hash",
        quantity=Decimal("100"),
        unit_nmck=Decimal("1000"),
        initial_price_value=Decimal("100000"),
        bid_security_amount=Decimal("1000"),
        contract_security_amount=Decimal("2000"),
        prepayment_percent=Decimal("20"),
        matched_keywords=[],
        excluded_keywords=[],
        attractiveness_score=0,
        attractiveness_level="low",
        attractiveness_reasons=[],
        normalized_item={},
        raw_item={},
        calculator_inputs={
            "fabric_price": "100",
            "fabric_consumption_per_unit": "2",
            "accessories_cost": "50",
            "sewing_cost": "100",
            "extra_operations_cost": "20",
            "logistics_cost": "10",
            "packaging_cost": "5",
            "defect_reserve_percent": "10",
            "admin_fot_cost": "1000",
        },
    )


class ProcurementCalculatorTests(unittest.TestCase):
    def test_calculates_default_vat_and_profit_tax_formula(self) -> None:
        result = calculate_procurement_lot(make_record())
        cautious = result["cautious"]

        self.assertTrue(cautious["complete"])
        self.assertEqual(cautious["vatRate"], "0.220000")
        self.assertEqual(cautious["profitTaxRate"], "0.250000")
        self.assertEqual(cautious["fabricCostPerUnit"], "200.00")
        self.assertEqual(cautious["unitCost"], "423.50")
        self.assertEqual(cautious["productionCost"], "42350.00")
        self.assertEqual(cautious["fullCost"], "43350.00")
        self.assertEqual(cautious["revenueWithoutVat"], "81967.21")
        self.assertEqual(cautious["grossProfit"], "38617.21")
        self.assertEqual(cautious["vatPayable"], "8495.79")
        self.assertEqual(cautious["profitTax"], "9654.30")
        self.assertEqual(cautious["netProfit"], "28962.91")
        self.assertEqual(cautious["profitability"], "0.353348")
        self.assertEqual(cautious["roi"], "0.668118")
        self.assertEqual(cautious["cashGapPeak"], "26350.00")

    def test_null_required_inputs_return_incomplete_scenarios(self) -> None:
        record = make_record()
        record.calculator_inputs = {"fabric_price": "100"}

        result = calculate_procurement_lot(record)

        self.assertFalse(result["cautious"]["complete"])
        self.assertIn("fabricConsumptionPerUnit", result["cautious"]["missingInputs"])

    def test_scenario_overrides_are_applied_and_cautious_is_persisted(self) -> None:
        record = make_record()
        record.calculator_inputs = {
            **record.calculator_inputs,
            "scenarios": {
                "optimistic": {"fabric_price": "80"},
                "cautious": {"fabric_price": "150"},
            },
        }

        scenarios = recalculate_procurement_lot(record)

        self.assertLess(Decimal(scenarios["optimistic"]["fullCost"]), Decimal(scenarios["realistic"]["fullCost"]))
        self.assertGreater(Decimal(scenarios["cautious"]["fullCost"]), Decimal(scenarios["realistic"]["fullCost"]))
        self.assertEqual(record.cost_realistic, Decimal("43350.00"))
        self.assertEqual(record.cost_cautious, Decimal(scenarios["cautious"]["fullCost"]))
        self.assertEqual(record.net_profit, Decimal(scenarios["cautious"]["netProfit"]))
        self.assertEqual(record.profitability, Decimal(scenarios["cautious"]["profitability"]))
        self.assertEqual(record.roi, Decimal(scenarios["cautious"]["roi"]))


if __name__ == "__main__":
    unittest.main()
