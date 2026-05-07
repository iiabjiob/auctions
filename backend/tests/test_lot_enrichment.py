from __future__ import annotations

import unittest
from datetime import UTC, datetime
from decimal import Decimal

from app.models.auction import AuctionLotDetailCache, AuctionLotRecord
from app.schemas.auctions import LotDatagridRow, LotFreshness, LotImage, LotRating
from app.services.lot_evidence import build_lot_evidence
from app.services.lot_enrichment import evaluate_lot_enrichment_requirements
from app.services.lot_enrichment import classify_lot_enrichment, schedule_lot_enrichment


def make_record() -> AuctionLotRecord:
    row = LotDatagridRow(
        row_id="tbankrot:auction-1:lot-1",
        source="tbankrot",
        source_title="TBankrot",
        auction_id="auction-1",
        auction_number="A-1",
        auction_name="Торги",
        lot_id="lot-1",
        lot_number="1",
        lot_name="Экскаватор гусеничный",
        lot_description="Подробное описание",
        category="Спецтехника",
        location="Московская область, Химки",
        location_region="Московская область",
        location_city="Химки",
        location_address="ул. Ленина, 1",
        location_coordinates="55.89, 37.45",
        model_category="Спецтехника",
        status="Идет прием заявок",
        initial_price="1 000 000 руб.",
        initial_price_value=Decimal("1000000"),
        current_price="900 000 руб.",
        current_price_value=Decimal("900000"),
        minimum_price="800 000 руб.",
        minimum_price_value=Decimal("800000"),
        price_schedule=[],
        images=[LotImage(url="https://example.test/image.jpg", source="detail")],
        primary_image_url="https://example.test/preview.jpg",
        image_count=1,
        application_deadline="05.05.2026 18:00",
        auction_date="07.05.2026 10:00",
        market_value=Decimal("2000000"),
        exclude_from_analysis=False,
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
        lot_name="Экскаватор гусеничный",
        status="Идет прием заявок",
        initial_price="1 000 000 руб.",
        content_hash="content-hash",
        is_new=True,
        datagrid_row=row.model_dump(mode="json"),
        normalized_item={
            "auction": {"publication_date": "01.05.2026", "application_deadline": "05.05.2026 18:00"},
            "lot": {
                "category": "Спецтехника",
                "region": "Московская область",
                "city": "Химки",
                "address": "ул. Ленина, 1",
                "coordinates": "55.89, 37.45",
                "inspection_order": "По записи",
                "description": "Подробное описание",
                "initial_price": "1 000 000 руб.",
                "current_price": "900 000 руб.",
                "minimum_price": "800 000 руб.",
                "market_value": "2 000 000 руб.",
            },
        },
    )


def make_detail_cache() -> AuctionLotDetailCache:
    return AuctionLotDetailCache(
        lot_record_id=1,
        content_hash="detail-hash",
        lot_detail={
            "lot": {
                "description": "Подробное описание",
                "inspection_order": "По записи",
                "category": "Спецтехника",
                "region": "Московская область",
                "city": "Химки",
                "address": "ул. Ленина, 1",
                "coordinates": "55.89, 37.45",
            },
            "raw_fields": [
                {"name": "Прием заявок", "value": "с 02.05.2026 09:00 до 05.05.2026 18:00"},
                {"name": "Проведение торгов", "value": "07.05.2026 10:00"},
            ],
        },
        auction_detail={"auction": {"publication_date": "01.05.2026"}},
        documents=[
            {"name": "photo.jpg", "url": "https://example.test/photo.jpg"},
            {"name": "Документы.pdf", "url": "https://example.test/doc.pdf"},
        ],
    )


def make_list_only_record(*, missing_price: bool = False, missing_location: bool = False, missing_category: bool = False, missing_deadline: bool = False) -> AuctionLotRecord:
    row = LotDatagridRow(
        row_id="tbankrot:auction-1:lot-1",
        source="tbankrot",
        source_title="TBankrot",
        auction_id="auction-1",
        auction_number="A-1",
        auction_name="Торги",
        lot_id="lot-1",
        lot_number="1",
        lot_name="Экскаватор гусеничный",
        lot_description="Подробное описание",
        category=None if missing_category else "Спецтехника",
        location=None if missing_location else "Московская область, Химки",
        location_region=None if missing_location else "Московская область",
        location_city=None if missing_location else "Химки",
        location_address=None if missing_location else "ул. Ленина, 1",
        location_coordinates=None if missing_location else "55.89, 37.45",
        model_category=None if missing_category else "Спецтехника",
        status="Идет прием заявок",
        initial_price=None if missing_price else "1 000 000 руб.",
        initial_price_value=None if missing_price else Decimal("1000000"),
        current_price=None if missing_price else "900 000 руб.",
        current_price_value=None if missing_price else Decimal("900000"),
        minimum_price=None if missing_price else "800 000 руб.",
        minimum_price_value=None if missing_price else Decimal("800000"),
        price_schedule=[],
        images=[],
        primary_image_url=None,
        image_count=0,
        application_deadline=None if missing_deadline else "05.05.2026 18:00",
        auction_date=None,
        market_value=None if missing_price else Decimal("2000000"),
        exclude_from_analysis=False,
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
        lot_name="Экскаватор гусеничный",
        status="Идет прием заявок",
        initial_price=None if missing_price else "1 000 000 руб.",
        content_hash="content-hash",
        is_new=True,
        datagrid_row=row.model_dump(mode="json"),
        normalized_item={
            "auction": {"publication_date": "01.05.2026", "application_deadline": None if missing_deadline else "05.05.2026 18:00"},
            "lot": {
                "category": None if missing_category else "Спецтехника",
                "region": None if missing_location else "Московская область",
                "city": None if missing_location else "Химки",
                "address": None if missing_location else "ул. Ленина, 1",
                "coordinates": None if missing_location else "55.89, 37.45",
                "description": "Подробное описание",
                "initial_price": None if missing_price else "1 000 000 руб.",
                "current_price": None if missing_price else "900 000 руб.",
                "minimum_price": None if missing_price else "800 000 руб.",
                "market_value": None if missing_price else "2 000 000 руб.",
            },
        },
    )


class LotEnrichmentRequirementTests(unittest.TestCase):
    def test_complete_local_evidence_does_not_need_enrichment(self) -> None:
        evidence = build_lot_evidence(make_record(), make_detail_cache())

        evaluation = evaluate_lot_enrichment_requirements(evidence)

        self.assertFalse(evaluation.needs_enrichment)
        self.assertEqual(evaluation.missing_fields, [])
        self.assertEqual(evaluation.reason_category, "ready_for_scoring")

    def test_missing_price_needs_enrichment(self) -> None:
        evidence = build_lot_evidence(make_record(), make_detail_cache())
        evidence = evidence.model_copy(
            update={"price": evidence.price.model_copy(update={"current_price": None, "initial_price": None, "minimum_price": None, "market_value": None})}
        )

        evaluation = evaluate_lot_enrichment_requirements(evidence)

        self.assertTrue(evaluation.needs_enrichment)
        self.assertIn("price", evaluation.missing_fields)

    def test_missing_location_category_deadline_needs_enrichment(self) -> None:
        evidence = build_lot_evidence(make_record(), make_detail_cache())
        evidence = evidence.model_copy(
            update={
                "location": evidence.location.model_copy(
                    update={"region": None, "city": None, "address": None, "coordinates": None}
                ),
                "category": evidence.category.model_copy(update={"category": None, "model_category": None}),
                "deadlines": evidence.deadlines.model_copy(
                    update={"application_start": None, "application_deadline": None, "auction_date": None, "hours_to_deadline": None}
                ),
            }
        )

        evaluation = evaluate_lot_enrichment_requirements(evidence)

        self.assertTrue(evaluation.needs_enrichment)
        self.assertCountEqual(evaluation.missing_fields, ["location", "category", "deadline"])
        self.assertEqual(evaluation.reason_category, "missing_first_pass_evidence")

    def test_optional_detail_only_fields_do_not_force_enrichment(self) -> None:
        evidence = build_lot_evidence(make_record(), make_detail_cache())
        evidence = evidence.model_copy(
            update={
                "legal": evidence.legal.model_copy(
                    update={"has_documents": False, "has_photos": False, "document_count": 0, "media_document_count": 0}
                ),
                "constraints": evidence.constraints.model_copy(
                    update={"inspection_order": None, "description_present": False, "price_schedule_steps": 0}
                ),
            }
        )

        evaluation = evaluate_lot_enrichment_requirements(evidence)

        self.assertFalse(evaluation.needs_enrichment)
        self.assertEqual(evaluation.missing_fields, [])

    def test_classify_lot_enrichment_marks_complete_list_record_locally_scorable(self) -> None:
        evaluation = classify_lot_enrichment(make_list_only_record())

        self.assertFalse(evaluation.needs_enrichment)
        self.assertEqual(evaluation.missing_fields, [])

    def test_classify_lot_enrichment_marks_missing_price_record_needing_enrichment(self) -> None:
        evaluation = classify_lot_enrichment(make_list_only_record(missing_price=True))

        self.assertTrue(evaluation.needs_enrichment)
        self.assertIn("price", evaluation.missing_fields)

    def test_schedule_lot_enrichment_sets_marker_for_missing_evidence(self) -> None:
        record = make_list_only_record(missing_price=True)
        evaluation = classify_lot_enrichment(record)

        changed = schedule_lot_enrichment(record, evaluation, requested_at=datetime(2026, 5, 7, tzinfo=UTC), force=True)

        self.assertTrue(changed)
        self.assertEqual(record.enrichment_requested_at, datetime(2026, 5, 7, tzinfo=UTC))

    def test_schedule_lot_enrichment_clears_marker_when_evidence_is_sufficient(self) -> None:
        record = make_list_only_record()
        record.enrichment_requested_at = datetime(2026, 5, 7, tzinfo=UTC)
        evaluation = classify_lot_enrichment(record)

        changed = schedule_lot_enrichment(record, evaluation)

        self.assertTrue(changed)
        self.assertIsNone(record.enrichment_requested_at)


if __name__ == "__main__":
    unittest.main()
