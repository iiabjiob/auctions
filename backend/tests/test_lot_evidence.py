from __future__ import annotations

import unittest
from decimal import Decimal

from app.models.auction import AuctionLotDetailCache, AuctionLotRecord
from app.schemas.auctions import LotDatagridRow, LotFreshness, LotImage, LotRating
from app.schemas.lot_evidence import build_lot_evidence_hash, build_lot_score_input_hash
from app.services.lot_evidence import build_lot_evidence, lot_evidence_hash


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


def make_detail_cache(*, reversed_top_level_order: bool = False) -> AuctionLotDetailCache:
    lot_payload = {
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
    }
    if reversed_top_level_order:
        lot_detail = dict([("raw_fields", lot_payload["raw_fields"]), ("lot", lot_payload["lot"])])
    else:
        lot_detail = dict([("lot", lot_payload["lot"]), ("raw_fields", lot_payload["raw_fields"])])

    return AuctionLotDetailCache(
        lot_record_id=1,
        content_hash="detail-hash",
        lot_detail=lot_detail,
        auction_detail={"auction": {"publication_date": "01.05.2026"}},
        documents=[
            {"name": "photo.jpg", "url": "https://example.test/photo.jpg"},
            {"name": "Документы.pdf", "url": "https://example.test/doc.pdf"},
        ],
    )


class LotEvidenceTests(unittest.TestCase):
    def test_build_lot_evidence_extracts_local_facts(self) -> None:
        record = make_record()
        detail_cache = make_detail_cache()

        evidence = build_lot_evidence(record, detail_cache)

        self.assertEqual(evidence.source_code, "tbankrot")
        self.assertEqual(evidence.price.current_price, Decimal("900000"))
        self.assertEqual(evidence.price.initial_price, Decimal("1000000"))
        self.assertEqual(evidence.location.region, "Московская область")
        self.assertEqual(evidence.location.city, "Химки")
        self.assertEqual(evidence.category.category, "Спецтехника")
        self.assertTrue(evidence.legal.has_documents)
        self.assertTrue(evidence.legal.has_photos)
        self.assertEqual(evidence.legal.document_count, 2)
        self.assertEqual(evidence.legal.media_document_count, 1)
        self.assertEqual(evidence.deadlines.application_start, "02.05.2026 09:00")
        self.assertEqual(evidence.deadlines.application_deadline, "05.05.2026 18:00")
        self.assertEqual(evidence.deadlines.auction_date, "07.05.2026 10:00")
        self.assertTrue(evidence.constraints.description_present)
        self.assertEqual(evidence.constraints.inspection_order, "По записи")
        self.assertTrue(evidence.freshness.is_new)

    def test_lot_evidence_hash_is_stable_for_equivalent_payloads(self) -> None:
        record = make_record()
        detail_cache_a = make_detail_cache(reversed_top_level_order=False)
        detail_cache_b = make_detail_cache(reversed_top_level_order=True)

        evidence_a = build_lot_evidence(record, detail_cache_a)
        evidence_b = build_lot_evidence(record, detail_cache_b)

        self.assertEqual(evidence_a.canonical_payload(), evidence_b.canonical_payload())
        self.assertEqual(build_lot_evidence_hash(evidence_a), build_lot_evidence_hash(evidence_b))
        self.assertEqual(lot_evidence_hash(record, detail_cache_a), lot_evidence_hash(record, detail_cache_b))

    def test_score_input_hash_uses_evidence_and_scoring_version(self) -> None:
        record = make_record()
        detail_cache = make_detail_cache()
        evidence = build_lot_evidence(record, detail_cache)

        first_hash = build_lot_score_input_hash(evidence, scoring_version="deterministic-v2")
        second_hash = build_lot_score_input_hash(evidence, scoring_version="deterministic-v2")
        changed_version_hash = build_lot_score_input_hash(evidence, scoring_version="deterministic-v3")
        changed_profile_hash = build_lot_score_input_hash(
            evidence,
            scoring_version="deterministic-v2",
            profile_identifier="profile-1",
        )

        self.assertEqual(first_hash, second_hash)
        self.assertNotEqual(first_hash, changed_version_hash)
        self.assertNotEqual(first_hash, changed_profile_hash)

    def test_score_input_hash_changes_when_evidence_changes(self) -> None:
        record = make_record()
        detail_cache = make_detail_cache()
        evidence = build_lot_evidence(record, detail_cache)
        changed_record = make_record()
        changed_record.datagrid_row["current_price"] = "850 000 руб."
        changed_record.datagrid_row["current_price_value"] = "850000"
        changed_record.normalized_item["lot"]["current_price"] = "850 000 руб."
        changed_evidence = build_lot_evidence(changed_record, detail_cache)

        first_hash = build_lot_score_input_hash(evidence, scoring_version="deterministic-v2")
        second_hash = build_lot_score_input_hash(changed_evidence, scoring_version="deterministic-v2")

        self.assertNotEqual(first_hash, second_hash)


if __name__ == "__main__":
    unittest.main()
