from __future__ import annotations

import unittest
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy.dialects import postgresql

from app.models.auction import AuctionLotDetailCache, AuctionLotRecord, AuctionLotWorkItem
from app.schemas.analysis_config import OwnerScoringProfile, ScoringDimensionWeights
from app.schemas.auctions import LotDatagridRow, LotFreshness, LotRating
from app.services import auction_catalog, auction_scoring, auction_sync, auction_workspace
from app.services.auction_datagrid_payload import validate_datagrid_row_payload
from app.services.auction_scoring import (
    SCORING_VERSION,
    build_record_score_input_hash,
    build_record_scoring_runtime_input,
    invalidate_lot_score,
    recalculate_record_rating,
    recalculate_record_rating_from_runtime_input,
    record_score_is_current,
)
from app.services.auction_scoring_invalidation import SOURCE_CONTENT_CHANGED
from app.services.lot_evidence import build_lot_evidence, build_lot_evidence_hash
from app.worker import auction_analysis_worker
from app.worker.auction_analysis_worker import _build_scoring_candidate_statement


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
        normalized_item={
            "auction": {"publication_date": "01.05.2026"},
            "lot": {
                "name": lot_name,
                "status": status,
                "category": "Спецтехника",
                "model_category": "Спецтехника",
                "region": "Московская область",
                "city": "Химки",
                "address": "ул. Ленина, 1",
                "coordinates": "55.89, 37.45",
            },
        },
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

    def test_rating_input_hash_includes_manual_scoring_inputs(self) -> None:
        record = make_record(lot_name="Экскаватор гусеничный")
        detail_cache = make_detail_cache()
        base_work_item = make_work_item()

        baseline_hash = build_record_score_input_hash(record, detail_cache, base_work_item)
        manual_variants = [
            ("decision_status", "bid"),
            ("final_decision", "approved"),
            ("exclude_from_analysis", True),
            ("exclusion_reason", "Manual exclusion"),
            ("category_override", "Спецтехника"),
            ("max_purchase_price", Decimal("1800000")),
            ("market_value", Decimal("2500000")),
            ("platform_fee", Decimal("10000")),
            ("delivery_cost", Decimal("20000")),
            ("dismantling_cost", Decimal("30000")),
            ("repair_cost", Decimal("40000")),
            ("storage_cost", Decimal("50000")),
            ("legal_cost", Decimal("60000")),
            ("other_costs", Decimal("70000")),
            ("target_profit", Decimal("80000")),
            ("analogs", [{"title": "Similar lot", "price": Decimal("123456")}]),
        ]

        for field, value in manual_variants:
            with self.subTest(field=field):
                work_item = make_work_item()
                setattr(work_item, field, value)
                self.assertNotEqual(
                    baseline_hash,
                    build_record_score_input_hash(record, detail_cache, work_item),
                )

    def test_record_scoring_runtime_input_matches_legacy_inputs(self) -> None:
        record = make_record(lot_name="Экскаватор гусеничный")
        detail_cache = make_detail_cache()
        work_item = make_work_item()

        adapter = build_record_scoring_runtime_input(record, detail_cache, work_item)
        payload = adapter.to_legacy_payload()

        self.assertEqual(payload["scoring_version"], SCORING_VERSION)
        self.assertEqual(payload["mode"], "record")
        self.assertEqual(payload["lot_evidence_hash"], build_lot_evidence_hash(build_lot_evidence(record, detail_cache)))
        self.assertEqual(payload["normalized_item"], record.normalized_item)
        self.assertEqual(payload["record_status"], record.status)
        self.assertEqual(payload["record_initial_price"], record.initial_price)
        self.assertEqual(payload["record_content_hash"], record.content_hash)
        self.assertEqual(payload["detail_content_hash"], detail_cache.content_hash)
        self.assertIs(payload["work_item"], work_item)
        self.assertEqual(payload["category_keywords"], None)
        self.assertEqual(payload["exclusion_keywords"], None)
        self.assertEqual(adapter.record_application_deadline, validate_datagrid_row_payload(record.datagrid_row).application_deadline)
        self.assertEqual(adapter.record_current_price, build_lot_evidence(record, detail_cache).price.current_price)
        self.assertEqual(adapter.record_market_value, work_item.market_value)
        self.assertEqual(adapter.record_location_region, build_lot_evidence(record, detail_cache).location.region)
        self.assertEqual(adapter.record_location_city, build_lot_evidence(record, detail_cache).location.city)
        self.assertEqual(adapter.record_category, build_lot_evidence(record, detail_cache).category.category)
        self.assertEqual(adapter.record_model_category, build_lot_evidence(record, detail_cache).category.model_category)
        self.assertEqual(adapter.record_has_documents, build_lot_evidence(record, detail_cache).legal.has_documents)
        self.assertEqual(adapter.record_has_photos, build_lot_evidence(record, detail_cache).legal.has_photos)
        self.assertEqual(adapter.record_legal_risk, "medium")
        self.assertFalse(adapter.record_is_excluded)
        self.assertIsNone(adapter.record_exclusion_keyword)

    def test_record_scoring_runtime_input_handles_missing_evidence_conservatively(self) -> None:
        record = make_record(lot_name="Экскаватор гусеничный")

        adapter = build_record_scoring_runtime_input(record, None, None)
        payload = adapter.to_legacy_payload()

        self.assertIsNone(payload["detail_content_hash"])
        self.assertIsNone(payload["work_item"])
        self.assertIsNone(payload["profile_identifier"])
        self.assertEqual(payload["lot_evidence_hash"], build_lot_evidence_hash(build_lot_evidence(record, None)))
        self.assertEqual(build_record_score_input_hash(record, None, None), build_record_score_input_hash(record, None, None))

    def test_record_scoring_runtime_input_uses_deadline_as_primary_source(self) -> None:
        record = make_record(lot_name="Экскаватор гусеничный")
        baseline_rating = recalculate_record_rating(record, None, None)
        runtime_input = build_record_scoring_runtime_input(record, None, None)
        runtime_input.record_application_deadline = "08.05.2026 12:00"
        record.datagrid_row["application_deadline"] = "09.05.2026 12:00"

        rating = recalculate_record_rating_from_runtime_input(record, None, runtime_input, force=True)

        self.assertEqual(baseline_rating.score, 63)
        self.assertEqual(rating.score, 77)
        self.assertEqual(rating.level, "high")
        self.assertIn("Есть срок окончания заявок", record.score_breakdown["dimensions"]["urgency"]["reasons"])
        self.assertEqual(rating.input_hash, record.score_input_hash)

    def test_record_scoring_runtime_input_uses_status_as_primary_source(self) -> None:
        record = make_record(lot_name="Товар")
        record.datagrid_row["status"] = "Лот отменен"
        record.normalized_item["lot"]["status"] = "Лот отменен"

        runtime_input = build_record_scoring_runtime_input(record, None, None)
        runtime_input.record_current_status = "Идет прием заявок"

        adapter_rating = recalculate_record_rating_from_runtime_input(record, None, runtime_input, force=True)
        adapter_breakdown = dict(record.score_breakdown)
        legacy_rating = recalculate_record_rating(record, None, None)

        self.assertEqual(legacy_rating.score, 0)
        self.assertEqual(legacy_rating.level, "low")
        self.assertEqual(adapter_rating.score, 63)
        self.assertEqual(adapter_rating.level, "medium")
        self.assertIn("Идет прием заявок", adapter_breakdown["reasons"])
        self.assertNotEqual(adapter_rating.input_hash, legacy_rating.input_hash)
        self.assertEqual(legacy_rating.input_hash, record.score_input_hash)

    def test_record_scoring_runtime_input_uses_current_price_as_primary_source(self) -> None:
        record = make_record(lot_name="Экскаватор гусеничный")
        record.initial_price = None
        record.datagrid_row["current_price"] = None
        record.datagrid_row["current_price_value"] = None
        baseline_rating = recalculate_record_rating(record, None, None)
        runtime_input = build_record_scoring_runtime_input(record, None, None)
        runtime_input.record_current_price = Decimal("1000000")

        rating = recalculate_record_rating_from_runtime_input(record, None, runtime_input, force=True)

        self.assertEqual(baseline_rating.score, 55)
        self.assertEqual(rating.score, 63)
        self.assertEqual(rating.level, "medium")
        self.assertIn("Цена распознана", record.score_breakdown["dimensions"]["data_quality"]["reasons"])
        self.assertEqual(rating.input_hash, record.score_input_hash)

    def test_record_scoring_runtime_input_uses_location_and_category_as_primary_source(self) -> None:
        target_profile = OwnerScoringProfile(
            target_regions=["Московская область"],
            target_categories=["Спецтехника"],
            max_budget=Decimal("2500000"),
            minimum_roi=Decimal("0.10"),
            minimum_market_discount=Decimal("0.10"),
        )

        preferred_record = make_record(lot_name="Товар")
        preferred_record.datagrid_row["location_region"] = "Новосибирская область"
        preferred_record.datagrid_row["location_city"] = "Новосибирск"
        preferred_record.datagrid_row["category"] = "Недвижимость"
        preferred_record.datagrid_row["model_category"] = "Недвижимость"
        preferred_record.normalized_item["lot"]["category"] = "Недвижимость"
        preferred_record.normalized_item["lot"]["model_category"] = "Недвижимость"
        preferred_runtime_input = build_record_scoring_runtime_input(preferred_record, None, None)
        preferred_runtime_input.record_location_region = "Московская область"
        preferred_runtime_input.record_location_city = "Химки"
        preferred_runtime_input.record_category = "Спецтехника"
        preferred_runtime_input.record_model_category = "Спецтехника"
        preferred_runtime_input.owner_profile = target_profile

        fallback_record = make_record(lot_name="Товар")
        fallback_record.datagrid_row["location_region"] = "Новосибирская область"
        fallback_record.datagrid_row["location_city"] = "Новосибирск"
        fallback_record.datagrid_row["category"] = "Недвижимость"
        fallback_record.datagrid_row["model_category"] = "Недвижимость"
        fallback_record.normalized_item["lot"]["category"] = "Недвижимость"
        fallback_record.normalized_item["lot"]["model_category"] = "Недвижимость"
        fallback_runtime_input = build_record_scoring_runtime_input(fallback_record, None, None)
        fallback_runtime_input.record_location_region = None
        fallback_runtime_input.record_location_city = None
        fallback_runtime_input.record_category = None
        fallback_runtime_input.record_model_category = None
        fallback_runtime_input.owner_profile = target_profile

        preferred_rating = recalculate_record_rating_from_runtime_input(preferred_record, None, preferred_runtime_input, force=True)
        fallback_rating = recalculate_record_rating_from_runtime_input(fallback_record, None, fallback_runtime_input, force=True)

        self.assertGreater(preferred_rating.score, fallback_rating.score)
        self.assertIn("Регион соответствует профилю", preferred_record.score_breakdown["dimensions"]["owner_fit"]["reasons"])
        self.assertIn("Категория соответствует профилю", preferred_record.score_breakdown["dimensions"]["owner_fit"]["reasons"])
        self.assertIn("Регион вне целевого профиля", fallback_record.score_breakdown["dimensions"]["owner_fit"]["reasons"])
        self.assertIn("Категория вне целевого профиля", fallback_record.score_breakdown["dimensions"]["owner_fit"]["reasons"])

    def test_record_scoring_runtime_input_uses_location_coordinates_as_primary_source(self) -> None:
        record = make_record(lot_name="Экскаватор гусеничный")
        record.datagrid_row["location_coordinates"] = "legacy-row-coordinates"
        runtime_input = build_record_scoring_runtime_input(record, None, None)
        runtime_input.record_location_coordinates = "adapter-coordinates"
        runtime_input.owner_profile = OwnerScoringProfile(max_delivery_distance_km=Decimal("25"))

        with patch("app.services.auction_scoring._apply_owner_profile_dimension", wraps=auction_scoring._apply_owner_profile_dimension) as apply_owner_profile:
            rating = recalculate_record_rating_from_runtime_input(record, None, runtime_input, force=True)

        apply_owner_profile.assert_called_once()
        self.assertEqual(apply_owner_profile.call_args.kwargs["location_coordinates"], "adapter-coordinates")
        self.assertEqual(rating.score, record.rating_score)
        self.assertEqual(rating.input_hash, record.score_input_hash)

    def test_record_scoring_runtime_input_uses_legal_document_media_as_primary_source(self) -> None:
        record = make_record(lot_name="Товар")
        detail_cache = make_detail_cache()

        runtime_input = build_record_scoring_runtime_input(record, detail_cache, None)
        legacy_rating = recalculate_record_rating(record, detail_cache, None)

        runtime_input.record_legal_risk = "high"
        runtime_input.record_is_excluded = True
        runtime_input.record_exclusion_keyword = "manual"
        adapter_rating = recalculate_record_rating_from_runtime_input(record, detail_cache, runtime_input, force=True)

        self.assertEqual(legacy_rating.score, 82)
        self.assertEqual(legacy_rating.level, "high")
        self.assertEqual(adapter_rating.score, 20)
        self.assertEqual(adapter_rating.level, "low")
        self.assertIn("Есть документы", record.score_breakdown["dimensions"]["data_quality"]["reasons"])
        self.assertIn("Есть фото или фотоархив", record.score_breakdown["dimensions"]["data_quality"]["reasons"])
        self.assertIn("Высокий юридический риск ограничивает рейтинг", record.score_breakdown["reasons"])
        self.assertIn("Лот исключен из анализа", record.score_breakdown["reasons"])
        self.assertEqual(legacy_rating.input_hash, adapter_rating.input_hash)

    def test_build_lot_analysis_prefers_adapter_category_and_risk_values(self) -> None:
        record = make_record(lot_name="Объект")
        detail_cache = make_detail_cache()
        detail_cache.lot_detail["lot"]["category"] = "Недвижимость"
        detail_cache.lot_detail["lot"]["description"] = "квартира в залоге"

        runtime_input = build_record_scoring_runtime_input(record, detail_cache, None)
        runtime_input.record_category = "Спецтехника"
        runtime_input.record_model_category = "Спецтехника"
        runtime_input.record_legal_risk = "low"
        runtime_input.record_is_excluded = True
        runtime_input.record_exclusion_keyword = "manual"

        rating = recalculate_record_rating_from_runtime_input(record, detail_cache, runtime_input, force=True)
        analysis = validate_datagrid_row_payload(record.datagrid_row).analysis

        self.assertEqual(analysis.category, "Спецтехника")
        self.assertEqual(analysis.legal_risk, "low")
        self.assertTrue(analysis.is_excluded)
        self.assertEqual(analysis.exclusion_keyword, "manual")
        self.assertEqual(rating.input_hash, build_record_score_input_hash(record, detail_cache, None))
        self.assertEqual(rating.scoring_version, SCORING_VERSION)

    def test_record_scoring_runtime_input_uses_documents_and_photos_as_primary_source(self) -> None:
        record = make_record(lot_name="Экскаватор гусеничный")
        detail_cache = make_detail_cache()
        runtime_input = build_record_scoring_runtime_input(record, detail_cache, None)

        baseline_rating = recalculate_record_rating_from_runtime_input(record, detail_cache, runtime_input, force=True)
        baseline_analysis = validate_datagrid_row_payload(record.datagrid_row).analysis

        self.assertEqual(baseline_analysis.completeness, "complete")
        self.assertGreaterEqual(baseline_rating.score, 82)

        runtime_input.record_has_documents = False
        runtime_input.record_has_photos = False
        adapter_rating = recalculate_record_rating_from_runtime_input(record, detail_cache, runtime_input, force=True)
        adapter_analysis = validate_datagrid_row_payload(record.datagrid_row).analysis

        self.assertEqual(adapter_analysis.completeness, "partial")
        self.assertIn("Нет документов", adapter_analysis.reasons)
        self.assertIn("Нет фото", adapter_analysis.reasons)
        self.assertLess(adapter_rating.score, baseline_rating.score)
        self.assertEqual(adapter_rating.input_hash, build_record_score_input_hash(record, detail_cache, None))

    def test_recalculate_record_rating_score_values_remain_unchanged_with_adapter(self) -> None:
        record = make_record(lot_name="Экскаватор гусеничный")
        detail_cache = make_detail_cache()
        work_item = make_work_item()

        rating = recalculate_record_rating(record, detail_cache, work_item)

        self.assertEqual(rating.score, record.rating_score)
        self.assertEqual(rating.level, record.rating_level)
        self.assertEqual(rating.input_hash, record.score_input_hash)

    def test_recalculate_record_rating_builds_runtime_adapter_first(self) -> None:
        record = make_record(lot_name="Экскаватор гусеничный")
        detail_cache = make_detail_cache()
        work_item = make_work_item()

        with patch("app.services.auction_scoring.build_record_scoring_runtime_input", wraps=build_record_scoring_runtime_input) as build_runtime_input:
            rating = recalculate_record_rating(record, detail_cache, work_item)

        build_runtime_input.assert_called_once()
        self.assertEqual(rating.score, record.rating_score)
        self.assertEqual(rating.input_hash, record.score_input_hash)

    def test_adapter_backed_scoring_regression_variants(self) -> None:
        cases = [
            {
                "name": "list_only_enough_evidence",
                "build": lambda: (make_record(lot_name="Экскаватор гусеничный"), None, None, 63, "medium"),
            },
            {
                "name": "detail_cache_evidence",
                "build": lambda: (make_record(lot_name="Экскаватор гусеничный"), make_detail_cache(), None, 82, "high"),
            },
            {
                "name": "missing_optional_detail_fields",
                "build": lambda: (
                    make_record(lot_name="Экскаватор гусеничный"),
                    self._make_detail_cache_without_auction_detail(),
                    None,
                    82,
                    "high",
                ),
            },
            {
                "name": "manual_workspace_economics",
                "build": lambda: (make_record(lot_name="Экскаватор гусеничный"), make_detail_cache(), make_work_item(), 100, "high"),
            },
            {
                "name": "weak_missing_evidence",
                "build": lambda: (
                    self._make_weak_missing_record(),
                    None,
                    None,
                    55,
                    "medium",
                ),
            },
        ]

        for case in cases:
            with self.subTest(case=case["name"]):
                record, detail_cache, work_item, expected_score, expected_level = case["build"]()
                adapter = build_record_scoring_runtime_input(record, detail_cache, work_item)
                expected_hash = build_record_score_input_hash(record, detail_cache, work_item)
                rating = recalculate_record_rating(record, detail_cache, work_item)

                self.assertEqual(rating.score, expected_score)
                self.assertEqual(rating.level, expected_level)
                self.assertEqual(rating.input_hash, expected_hash)
                self.assertEqual(expected_hash, build_record_score_input_hash(record, detail_cache, work_item))
                self.assertEqual(adapter.lot_evidence_hash, build_lot_evidence_hash(build_lot_evidence(record, detail_cache)))
                self.assertEqual(adapter.scoring_version, SCORING_VERSION)
                self.assertEqual(adapter.record_content_hash, record.content_hash)
                self.assertEqual(adapter.record_status, record.status)
                if detail_cache is not None:
                    self.assertEqual(adapter.detail_content_hash, detail_cache.content_hash)
                else:
                    self.assertIsNone(adapter.detail_content_hash)
                if work_item is not None:
                    self.assertIs(adapter.work_item, work_item)
                else:
                    self.assertIsNone(adapter.work_item)

    def test_rating_input_hash_ignores_ui_only_manual_fields(self) -> None:
        record = make_record(lot_name="Экскаватор гусеничный")
        detail_cache = make_detail_cache()
        work_item = make_work_item()

        baseline_hash = build_record_score_input_hash(record, detail_cache, work_item)
        work_item.inspection_result = "Нужна повторная проверка"
        work_item.inspection_at = None

        self.assertEqual(baseline_hash, build_record_score_input_hash(record, detail_cache, work_item))

    def test_recalculate_skips_when_input_hash_is_unchanged_and_score_state_is_complete(self) -> None:
        record = make_record(lot_name="Экскаватор гусеничный")
        detail_cache = make_detail_cache()
        work_item = make_work_item()

        recalculate_record_rating(record, detail_cache, work_item)
        stored_hash = record.score_input_hash

        with patch("app.services.auction_scoring.build_lot_analysis", wraps=auction_scoring.build_lot_analysis) as build_analysis:
            rating = recalculate_record_rating(record, detail_cache, work_item)

        self.assertEqual(stored_hash, record.score_input_hash)
        self.assertEqual(rating.input_hash, stored_hash)
        build_analysis.assert_not_called()

    def test_invalidate_lot_score_preserves_ui_score_state(self) -> None:
        record = make_record(lot_name="Экскаватор гусеничный")
        detail_cache = make_detail_cache()
        work_item = make_work_item()

        rating = recalculate_record_rating(record, detail_cache, work_item)
        original_breakdown = record.score_breakdown
        original_score = record.rating_score

        invalidate_lot_score(record, reason=SOURCE_CONTENT_CHANGED)

        self.assertIsNone(record.score_input_hash)
        self.assertEqual(record.rating_score, original_score)
        self.assertEqual(record.score_breakdown, original_breakdown)
        self.assertFalse(record_score_is_current(record, input_hash=rating.input_hash))

    def test_rating_input_hash_changes_when_local_evidence_changes(self) -> None:
        record = make_record(lot_name="Экскаватор гусеничный")
        detail_cache = make_detail_cache()
        work_item = make_work_item()

        first_hash = build_record_score_input_hash(record, detail_cache, work_item)
        detail_cache.lot_detail["lot"]["region"] = "Самарская область"
        second_hash = build_record_score_input_hash(record, detail_cache, work_item)

        self.assertNotEqual(first_hash, second_hash)

    def test_recalculate_runs_when_local_evidence_changes(self) -> None:
        record = make_record(lot_name="Экскаватор гусеничный")
        detail_cache = make_detail_cache()
        work_item = make_work_item()

        recalculate_record_rating(record, detail_cache, work_item)
        detail_cache.lot_detail["lot"]["region"] = "Самарская область"

        with patch("app.services.auction_scoring.build_lot_analysis", wraps=auction_scoring.build_lot_analysis) as build_analysis:
            recalculate_record_rating(record, detail_cache, work_item)

        build_analysis.assert_called_once()

    def test_invalidation_triggers_rescore_and_persists_new_hash(self) -> None:
        record = make_record(lot_name="Экскаватор гусеничный")
        detail_cache = make_detail_cache()
        work_item = make_work_item()

        first_rating = recalculate_record_rating(record, detail_cache, work_item)
        invalidate_lot_score(record, reason=SOURCE_CONTENT_CHANGED)

        second_rating = recalculate_record_rating(record, detail_cache, work_item)

        self.assertEqual(second_rating.score, first_rating.score)
        self.assertEqual(record.score_input_hash, second_rating.input_hash)
        self.assertEqual(record.scoring_version, SCORING_VERSION)

    def test_recalculate_runs_when_score_breakdown_is_missing(self) -> None:
        record = make_record(lot_name="Экскаватор гусеничный")
        detail_cache = make_detail_cache()
        work_item = make_work_item()

        recalculate_record_rating(record, detail_cache, work_item)
        record.score_breakdown = {}
        record.scored_at = None

        with patch("app.services.auction_scoring.build_lot_analysis", wraps=auction_scoring.build_lot_analysis) as build_analysis:
            recalculate_record_rating(record, detail_cache, work_item)

        build_analysis.assert_called_once()

    def test_scoring_candidate_statement_includes_incomplete_score_state(self) -> None:
        statement = _build_scoring_candidate_statement(("tbankrot",))
        compiled = statement.compile(dialect=postgresql.dialect())
        sql = str(compiled)

        self.assertIn("auction_lot_records.scoring_version !=", sql)
        self.assertIn("auction_lot_records.score_input_hash IS NULL", sql)
        self.assertIn("auction_lot_records.scored_at IS NULL", sql)
        self.assertIn("auction_lot_records.score_breakdown", sql)
        self.assertIn("auction_lot_records.scoring_version", sql)

    def test_recalculate_runs_when_scoring_version_changes(self) -> None:
        record = make_record(lot_name="Экскаватор гусеничный")
        detail_cache = make_detail_cache()
        work_item = make_work_item()

        recalculate_record_rating(record, detail_cache, work_item)
        record.scoring_version = "old-version"

        with patch("app.services.auction_scoring.build_lot_analysis", wraps=auction_scoring.build_lot_analysis) as build_analysis:
            recalculate_record_rating(record, detail_cache, work_item)

        build_analysis.assert_called_once()

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

    @staticmethod
    def _make_weak_missing_record() -> AuctionLotRecord:
        record = make_record(lot_name="Экскаватор гусеничный")
        record.initial_price = None
        record.datagrid_row["current_price"] = None
        record.datagrid_row["current_price_value"] = None
        record.normalized_item["lot"]["initial_price"] = None
        return record

    @staticmethod
    def _make_detail_cache_without_auction_detail() -> AuctionLotDetailCache:
        detail_cache = make_detail_cache()
        detail_cache.auction_detail = None
        return detail_cache


if __name__ == "__main__":
    unittest.main()
