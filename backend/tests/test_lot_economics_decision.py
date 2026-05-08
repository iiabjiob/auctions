from __future__ import annotations

import unittest
from decimal import Decimal

from app.models.auction import AuctionLotDetailCache, AuctionLotRecord, AuctionLotWorkItem
from app.schemas.auctions import LotDatagridRow, LotFreshness, LotRating
from app.schemas.scoring_profile import LotScoringProfile
from app.services.lot_decision_report import (
    build_lot_decision_report,
    calculate_lot_economics_decision,
)


def make_record(*, market_value: str | None = "2000000 RUB") -> AuctionLotRecord:
    row = LotDatagridRow(
        row_id="tbankrot:auction-1:lot-1",
        source="tbankrot",
        source_title="TBankrot",
        auction_id="auction-1",
        lot_id="lot-1",
        lot_name="Tracked excavator",
        current_price="1000000 RUB",
        current_price_value=Decimal("1000000"),
        location_region="Moscow Oblast",
        freshness=LotFreshness(is_new=True),
        rating=LotRating(score=88, level="high", reasons=[]),
    )
    lot_payload = {
        "category": "Special equipment",
        "region": "Moscow Oblast",
        "current_price": "1000000 RUB",
    }
    if market_value is not None:
        lot_payload["market_value"] = market_value
    return AuctionLotRecord(
        id=1,
        source_code="tbankrot",
        auction_external_id="auction-1",
        lot_external_id="lot-1",
        lot_name="Tracked excavator",
        status="Accepting applications",
        initial_price="1000000 RUB",
        content_hash="content-hash",
        rating_score=88,
        rating_level="high",
        score_breakdown={"reasons": ["Price recognized"], "caps": [], "inputs": {}},
        datagrid_row=row.model_dump(mode="json"),
        normalized_item={"auction": {}, "lot": lot_payload},
    )


def make_detail_cache() -> AuctionLotDetailCache:
    return AuctionLotDetailCache(
        lot_record_id=1,
        content_hash="detail-hash",
        lot_detail={"lot": {"description": "Local detail payload"}},
        auction_detail=None,
        documents=[{"name": "documents.pdf"}],
    )


class LotEconomicsDecisionTests(unittest.TestCase):
    def test_complete_inputs_produce_max_buy_price(self) -> None:
        economics = calculate_lot_economics_decision(
            make_record(),
            detail_cache=make_detail_cache(),
            work_item=AuctionLotWorkItem(
                lot_record_id=1,
                market_value=Decimal("2200000"),
                platform_fee=Decimal("100000"),
            ),
            target_roi=Decimal("0.25"),
        )

        self.assertEqual(economics.current_price, Decimal("1000000"))
        self.assertEqual(economics.market_value, Decimal("2200000"))
        self.assertEqual(economics.expected_costs, Decimal("100000"))
        self.assertEqual(economics.max_buy_price, Decimal("1680000"))
        self.assertEqual(economics.estimated_profit, Decimal("1100000"))
        self.assertEqual(economics.confidence, "high")

    def test_missing_market_value_does_not_invent_result(self) -> None:
        economics = calculate_lot_economics_decision(
            make_record(market_value=None),
            detail_cache=make_detail_cache(),
            work_item=AuctionLotWorkItem(lot_record_id=1, delivery_cost=Decimal("50000")),
        )

        self.assertIsNone(economics.market_value)
        self.assertIsNone(economics.max_buy_price)
        self.assertIsNone(economics.estimated_profit)
        self.assertEqual(economics.confidence, "low")
        self.assertIn("market_value", economics.missing_inputs)

    def test_expected_costs_reduce_max_buy_price(self) -> None:
        without_costs = calculate_lot_economics_decision(
            make_record(),
            detail_cache=make_detail_cache(),
            target_roi=Decimal("0.25"),
        )
        with_costs = calculate_lot_economics_decision(
            make_record(),
            detail_cache=make_detail_cache(),
            work_item=AuctionLotWorkItem(lot_record_id=1, repair_cost=Decimal("250000")),
            target_roi=Decimal("0.25"),
        )

        self.assertEqual(without_costs.max_buy_price, Decimal("1600000"))
        self.assertEqual(with_costs.max_buy_price, Decimal("1400000"))
        self.assertLess(with_costs.max_buy_price, without_costs.max_buy_price)

    def test_target_roi_changes_max_buy_price(self) -> None:
        conservative = calculate_lot_economics_decision(
            make_record(),
            detail_cache=make_detail_cache(),
            target_roi=Decimal("0.50"),
        )
        balanced = calculate_lot_economics_decision(
            make_record(),
            detail_cache=make_detail_cache(),
            target_roi=Decimal("0.25"),
        )
        expected_conservative = Decimal("2000000") / Decimal("1.50")

        self.assertEqual(conservative.max_buy_price, expected_conservative)
        self.assertEqual(balanced.max_buy_price, Decimal("1600000"))
        self.assertLess(conservative.max_buy_price, balanced.max_buy_price)

    def test_builder_wires_economics_object_into_report(self) -> None:
        profile = LotScoringProfile(minimum_roi=Decimal("0.30"))

        report = build_lot_decision_report(
            make_record(),
            detail_cache=make_detail_cache(),
            profile=profile,
        )

        self.assertIsNotNone(report.economics)
        self.assertEqual(report.economics.target_roi, Decimal("0.30"))
        self.assertEqual(report.economics.market_value, Decimal("2000000"))


if __name__ == "__main__":
    unittest.main()
