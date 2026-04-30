from __future__ import annotations

import unittest
from decimal import Decimal

from app.models.auction import AuctionLotDetailCache, AuctionLotRecord, AuctionLotWorkItem
from app.schemas.analysis_config import OwnerScoringProfile, ScoringDimensionWeights
from app.schemas.auctions import LotDatagridRow, LotFreshness, LotRating
from app.services import auction_catalog, auction_scoring, auction_sync, auction_workspace
from app.services.auction_datagrid_payload import validate_datagrid_row_payload
from app.services.auction_scoring import (
    SCORING_VERSION,
    build_record_score_input_hash,
    recalculate_record_rating,
    record_score_is_current,
)
from app.worker import auction_analysis_worker


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


def score_cap_keys(record: AuctionLotRecord) -> list[str]:
    return [cap["key"] for cap in record.score_breakdown["caps"]]


class AuctionRatingTests(unittest.TestCase):
    def test_rating_entry_points_use_canonical_scoring_module(self) -> None:
        self.assertIs(auction_catalog.calculate_list_lot_rating, auction_scoring.calculate_list_lot_rating)
        self.assertIs(auction_sync.recalculate_record_rating, auction_scoring.recalculate_record_rating)
        self.assertIs(auction_workspace.recalculate_record_rating, auction_scoring.recalculate_record_rating)
        self.assertIs(auction_analysis_worker.recalculate_record_rating, auction_scoring.recalculate_record_rating)

    def test_profitable_operational_lot_gets_high_rating(self) -> None:
        record = make_record(lot_name="Экскаватор гусеничный")
        rating = recalculate_record_rating(record, make_detail_cache(), make_work_item())

        self.assertEqual(rating.level, "high")
        self.assertGreaterEqual(rating.score, 90)
        self.assertIn("Дисконт к рынку 50%+", rating.reasons)
        self.assertIn("ROI 50%+", rating.reasons)
        self.assertEqual(record.scoring_version, SCORING_VERSION)
        self.assertEqual(rating.scoring_version, SCORING_VERSION)
        self.assertIsNotNone(record.scored_at)
        self.assertEqual(record.score_input_hash, rating.input_hash)
        self.assertEqual(record.score_breakdown["version"], SCORING_VERSION)
        self.assertEqual(record.score_breakdown["mode"], "record")
        self.assertGreater(record.score_breakdown["dimensions"]["economics"]["score"], 0)
        self.assertGreater(record.score_breakdown["dimensions"]["data_quality"]["score"], 0)
        self.assertIn("owner_fit", record.score_breakdown["dimensions"])

    def test_rating_input_hash_is_stable_for_unchanged_inputs(self) -> None:
        record = make_record(lot_name="Экскаватор гусеничный")
        detail_cache = make_detail_cache()
        work_item = make_work_item()

        first_rating = recalculate_record_rating(record, detail_cache, work_item)
        first_hash = record.score_input_hash
        second_rating = recalculate_record_rating(record, detail_cache, work_item)

        self.assertEqual(first_hash, record.score_input_hash)
        self.assertEqual(first_rating.input_hash, second_rating.input_hash)
        self.assertEqual(second_rating.breakdown["score"], second_rating.score)

    def test_score_current_detection_uses_version_and_input_hash(self) -> None:
        record = make_record(lot_name="Экскаватор гусеничный")
        detail_cache = make_detail_cache()
        work_item = make_work_item()

        recalculate_record_rating(record, detail_cache, work_item)
        input_hash = build_record_score_input_hash(record, detail_cache, work_item)

        self.assertTrue(record_score_is_current(record, input_hash=input_hash))

        record.scoring_version = "old-version"
        self.assertFalse(record_score_is_current(record, input_hash=input_hash))

        record.scoring_version = SCORING_VERSION
        work_item.market_value = Decimal("2500000")
        next_hash = build_record_score_input_hash(record, detail_cache, work_item)
        self.assertFalse(record_score_is_current(record, input_hash=next_hash))

    def test_excluded_keyword_caps_rating_even_with_good_economics(self) -> None:
        record = make_record(lot_name="Квартира с дисконтом")
        rating = recalculate_record_rating(record, make_detail_cache(), make_work_item())
        row = LotDatagridRow.model_validate(record.datagrid_row)

        self.assertTrue(row.analysis.is_excluded)
        self.assertLessEqual(rating.score, 20)
        self.assertEqual(rating.level, "low")
        self.assertIn("excluded", score_cap_keys(record))

    def test_manual_reject_caps_rating_even_with_good_economics(self) -> None:
        record = make_record(lot_name="Экскаватор гусеничный")
        rating = recalculate_record_rating(record, make_detail_cache(), make_work_item(decision_status="reject"))

        self.assertLessEqual(rating.score, 20)
        self.assertEqual(rating.level, "low")
        self.assertIn("Команда отметила отказ", rating.reasons)
        self.assertIn("manual_reject", score_cap_keys(record))

    def test_high_legal_risk_caps_rating(self) -> None:
        record = make_record(lot_name="Экскаватор в залоге")
        rating = recalculate_record_rating(record, make_detail_cache(), make_work_item())
        row = LotDatagridRow.model_validate(record.datagrid_row)

        self.assertEqual(row.analysis.legal_risk, "high")
        self.assertLessEqual(rating.score, 44)
        self.assertNotEqual(rating.level, "high")
        self.assertIn("high_legal_risk", score_cap_keys(record))

    def test_manual_bid_can_approve_high_legal_risk_for_rating(self) -> None:
        record = make_record(lot_name="Экскаватор в залоге")
        rating = recalculate_record_rating(record, make_detail_cache(), make_work_item(decision_status="bid"))
        row = LotDatagridRow.model_validate(record.datagrid_row)

        self.assertEqual(row.analysis.legal_risk, "high")
        self.assertEqual(rating.level, "high")
        self.assertNotIn("high_legal_risk", score_cap_keys(record))

    def test_cancelled_lot_caps_rating_to_low_priority(self) -> None:
        record = make_record(lot_name="Экскаватор гусеничный", status="Лот отменен")
        rating = recalculate_record_rating(record, make_detail_cache(), make_work_item())

        self.assertLessEqual(rating.score, 20)
        self.assertEqual(rating.level, "low")
        self.assertIn("cancelled", score_cap_keys(record))

    def test_completed_lot_caps_rating_to_low_priority(self) -> None:
        record = make_record(lot_name="Экскаватор гусеничный", status="Торги завершены")
        rating = recalculate_record_rating(record, make_detail_cache(), make_work_item())

        self.assertLessEqual(rating.score, 20)
        self.assertEqual(rating.level, "low")
        self.assertIn("non_actionable", score_cap_keys(record))

    def test_missing_price_caps_rating_below_high(self) -> None:
        record = make_record(lot_name="Экскаватор гусеничный")
        record.initial_price = None
        record.datagrid_row["current_price"] = None
        record.datagrid_row["current_price_value"] = None
        record.normalized_item["lot"]["initial_price"] = None
        detail_cache = make_detail_cache()
        rating = recalculate_record_rating(record, detail_cache, make_work_item(decision_status="bid"))

        self.assertEqual(rating.score, 69)
        self.assertEqual(rating.level, "medium")
        self.assertIn("missing_price", score_cap_keys(record))

    def test_owner_profile_matching_lot_increases_owner_fit(self) -> None:
        record = make_record(lot_name="Экскаватор гусеничный")
        detail_cache = make_detail_cache()
        detail_cache.lot_detail["lot"]["region"] = "Московская область"
        detail_cache.lot_detail["lot"]["category"] = "Спецтехника"
        profile = OwnerScoringProfile(
            target_regions=["Московская область"],
            target_categories=["Спецтехника"],
            max_budget=Decimal("1500000"),
            minimum_roi=Decimal("0.40"),
            minimum_market_discount=Decimal("0.40"),
            require_documents=True,
            require_photos=True,
        )

        rating = recalculate_record_rating(record, detail_cache, make_work_item(), owner_profile=profile)
        owner_fit = record.score_breakdown["dimensions"]["owner_fit"]

        self.assertEqual(rating.level, "high")
        self.assertGreater(owner_fit["score"], 0)
        self.assertIn("Регион соответствует профилю", owner_fit["reasons"])
        self.assertIn("Категория соответствует профилю", owner_fit["reasons"])

    def test_owner_profile_mismatch_lowers_same_lot_score_and_changes_hash(self) -> None:
        record = make_record(lot_name="Экскаватор гусеничный")
        detail_cache = make_detail_cache()
        detail_cache.lot_detail["lot"]["region"] = "Московская область"
        detail_cache.lot_detail["lot"]["category"] = "Спецтехника"
        work_item = make_work_item(dismantling_cost=Decimal("100000"))
        matching_profile = OwnerScoringProfile(
            target_regions=["Московская область"],
            target_categories=["Спецтехника"],
            max_budget=Decimal("1500000"),
            minimum_roi=Decimal("0.40"),
            minimum_market_discount=Decimal("0.40"),
        )
        mismatching_profile = OwnerScoringProfile(
            target_regions=["Новосибирская область"],
            target_categories=["Недвижимость"],
            max_budget=Decimal("500000"),
            minimum_roi=Decimal("0.90"),
            minimum_market_discount=Decimal("0.80"),
            excluded_terms=["экскаватор"],
            discouraged_terms=["гусеничный"],
            allow_dismantling=False,
        )

        matching_rating = recalculate_record_rating(record, detail_cache, work_item, owner_profile=matching_profile)
        matching_hash = record.score_input_hash
        mismatching_rating = recalculate_record_rating(record, detail_cache, work_item, owner_profile=mismatching_profile)
        owner_fit = record.score_breakdown["dimensions"]["owner_fit"]

        self.assertNotEqual(matching_hash, record.score_input_hash)
        self.assertLess(mismatching_rating.score, matching_rating.score)
        self.assertLess(owner_fit["score"], 0)
        self.assertIn("Профиль исключает термин: экскаватор", owner_fit["reasons"])

    def test_dimension_weights_affect_weighted_score(self) -> None:
        record = make_record(lot_name="Экскаватор гусеничный")
        detail_cache = make_detail_cache()
        detail_cache.lot_detail["lot"]["region"] = "Московская область"
        detail_cache.lot_detail["lot"]["category"] = "Спецтехника"
        profile = OwnerScoringProfile(
            target_regions=["Новосибирская область"],
            target_categories=["Недвижимость"],
            max_budget=Decimal("500000"),
            minimum_roi=Decimal("0.90"),
            minimum_market_discount=Decimal("0.80"),
            excluded_terms=["экскаватор"],
        )

        weighted_rating = recalculate_record_rating(
            record,
            detail_cache,
            make_work_item(),
            owner_profile=profile,
            dimension_weights=ScoringDimensionWeights(owner_fit=Decimal("0")),
        )
        owner_fit = record.score_breakdown["dimensions"]["owner_fit"]

        self.assertEqual(owner_fit["weighted_score"], 0)
        self.assertGreaterEqual(weighted_rating.score, 90)

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
