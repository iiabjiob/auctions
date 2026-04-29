from __future__ import annotations

import unittest
from decimal import Decimal

from app.models.auction import AuctionLotDetailCache, AuctionLotRecord, AuctionLotWorkItem
from app.schemas.auctions import LotDatagridRow, LotFreshness, LotRating
from app.services.auction_catalog import validate_datagrid_row_payload
from app.services.auction_workspace import recalculate_record_rating


def make_record(*, lot_name: str, status: str = "Идет прием заявок") -> AuctionLotRecord:
    row = LotDatagridRow(
        row_id="tbankrot:auction-1:lot-1",
        source="tbankrot",
        source_title="TBankrot",
        auction_id="auction-1",
        auction_number="A-1",
        lot_id="lot-1",
        lot_number="1",
        lot_name=lot_name,
        status=status,
        current_price="1 000 000 руб.",
        current_price_value=Decimal("1000000"),
        freshness=LotFreshness(is_new=True),
        rating=LotRating(score=0, level="low", reasons=[]),
    )
    return AuctionLotRecord(
        id=1,
        source_code="tbankrot",
        auction_external_id="auction-1",
        lot_external_id="lot-1",
        auction_number="A-1",
        lot_number="1",
        lot_name=lot_name,
        status=status,
        initial_price="1 000 000 руб.",
        content_hash="hash",
        datagrid_row=row.model_dump(mode="json"),
        normalized_item={"lot": {"name": lot_name, "status": status}},
    )


def make_detail_cache() -> AuctionLotDetailCache:
    return AuctionLotDetailCache(
        lot_record_id=1,
        content_hash="detail-hash",
        lot_detail={"lot": {"description": "Подробное описание", "inspection_order": "По записи"}},
        auction_detail=None,
        documents=[{"name": "photo.jpg", "url": "https://example.test/photo.jpg"}, {"name": "Документы.pdf"}],
    )


def make_work_item(**overrides: object) -> AuctionLotWorkItem:
    values = {
        "lot_record_id": 1,
        "market_value": Decimal("2000000"),
        "platform_fee": Decimal("0"),
        "delivery_cost": Decimal("0"),
        "dismantling_cost": Decimal("0"),
        "repair_cost": Decimal("0"),
        "storage_cost": Decimal("0"),
        "legal_cost": Decimal("0"),
        "other_costs": Decimal("0"),
        "target_profit": Decimal("300000"),
        "analogs": [],
    }
    values.update(overrides)
    return AuctionLotWorkItem(**values)


class AuctionRatingTests(unittest.TestCase):
    def test_profitable_operational_lot_gets_high_rating(self) -> None:
        record = make_record(lot_name="Экскаватор гусеничный")
        rating = recalculate_record_rating(record, make_detail_cache(), make_work_item())

        self.assertEqual(rating.level, "high")
        self.assertGreaterEqual(rating.score, 90)
        self.assertIn("Дисконт к рынку 50%+", rating.reasons)
        self.assertIn("ROI 50%+", rating.reasons)

    def test_excluded_keyword_caps_rating_even_with_good_economics(self) -> None:
        record = make_record(lot_name="Квартира с дисконтом")
        rating = recalculate_record_rating(record, make_detail_cache(), make_work_item())
        row = LotDatagridRow.model_validate(record.datagrid_row)

        self.assertTrue(row.analysis.is_excluded)
        self.assertLessEqual(rating.score, 20)
        self.assertEqual(rating.level, "low")

    def test_manual_reject_caps_rating_even_with_good_economics(self) -> None:
        record = make_record(lot_name="Экскаватор гусеничный")
        rating = recalculate_record_rating(record, make_detail_cache(), make_work_item(decision_status="reject"))

        self.assertLessEqual(rating.score, 20)
        self.assertEqual(rating.level, "low")
        self.assertIn("Команда отметила отказ", rating.reasons)

    def test_high_legal_risk_caps_rating(self) -> None:
        record = make_record(lot_name="Экскаватор в залоге")
        rating = recalculate_record_rating(record, make_detail_cache(), make_work_item())
        row = LotDatagridRow.model_validate(record.datagrid_row)

        self.assertEqual(row.analysis.legal_risk, "high")
        self.assertLessEqual(rating.score, 44)
        self.assertNotEqual(rating.level, "high")

    def test_formatted_market_value_from_persisted_row_is_sanitized(self) -> None:
        record = make_record(lot_name="Экскаватор гусеничный")
        record.datagrid_row["market_value"] = "4 549 608 ₽"
        record.datagrid_row["exclude_from_analysis"] = None

        row = validate_datagrid_row_payload(record.datagrid_row)
        rating = recalculate_record_rating(record, None, None)

        self.assertEqual(row.market_value, Decimal("4549608"))
        self.assertFalse(row.exclude_from_analysis)
        self.assertIsInstance(rating.score, int)


if __name__ == "__main__":
    unittest.main()
