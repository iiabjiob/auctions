from __future__ import annotations

import unittest
from decimal import Decimal

from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from app.models.auction import AuctionLotRecord
from app.models.auction import AuctionLotDetailCache, AuctionLotWorkItem
from app.models.scoring_profile import ScoringProfileModel
from app.schemas.auctions import LotDatagridRow, LotFreshness, LotRating
from app.schemas.scoring_profile import LotScoringProfile, build_lot_scoring_profile_hash
from app.services.auction_scoring import recalculate_record_rating
from app.services.scoring_profile_store import scoring_profile_store_service


class FakeSession:
    def __init__(self, scalar_result: ScoringProfileModel | None = None) -> None:
        self.scalar_result = scalar_result
        self.statements = []
        self.added: list[object] = []
        self.commits = 0
        self.refreshed: list[object] = []

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.commits += 1

    async def refresh(self, obj: object) -> None:
        self.refreshed.append(obj)

    async def scalar(self, statement):  # noqa: ANN001
        self.statements.append(statement)
        return self.scalar_result


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
        status="Идет прием заявок",
        initial_price="1 000 000 руб.",
        current_price="900 000 руб.",
        current_price_value=Decimal("900000"),
        application_deadline="05.05.2026 18:00",
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
        datagrid_row=row.model_dump(mode="json"),
        normalized_item={"auction": {"application_deadline": "05.05.2026 18:00"}, "lot": {"category": "Спецтехника", "region": "Московская область"}},
    )


def make_detail_cache() -> AuctionLotDetailCache:
    return AuctionLotDetailCache(
        lot_record_id=1,
        content_hash="detail-hash",
        lot_detail={"lot": {"description": "Подробное описание"}},
        auction_detail=None,
        documents=[{"name": "photo.jpg"}],
    )


def make_work_item() -> AuctionLotWorkItem:
    return AuctionLotWorkItem(
        lot_record_id=1,
        market_value=Decimal("2000000"),
        platform_fee=Decimal("0"),
        delivery_cost=Decimal("0"),
        dismantling_cost=Decimal("0"),
        repair_cost=Decimal("0"),
        storage_cost=Decimal("0"),
        legal_cost=Decimal("0"),
        other_costs=Decimal("0"),
        target_profit=Decimal("300000"),
        analogs=[],
    )


class ScoringProfileStoreTests(unittest.IsolatedAsyncioTestCase):
    def test_build_profile_record_normalizes_and_hashes_payload(self) -> None:
        payload = {
            "profile_identifier": "profile-1",
            "target_regions": ["Москва", "Московская область"],
            "target_categories": ["Оборудование", "Спецтехника"],
            "allowed_legal_risks": ["medium", "low"],
            "stop_words": ["квартира", "личные вещи"],
            "desired_keywords": ["погрузчик", "экскаватор"],
            "weights": {"profile_fit.blocker_penalty": Decimal("-2"), "profile_fit.match_bonus": Decimal("7")},
        }

        record = scoring_profile_store_service.build_profile_record("  Main profile  ", payload, is_active=True)
        normalized_profile = LotScoringProfile.model_validate({**payload, "profile_identifier": "profile-1"})

        self.assertEqual(record.name, "Main profile")
        self.assertEqual(record.profile_identifier, "profile-1")
        self.assertEqual(record.profile_payload, normalized_profile.canonical_payload())
        self.assertEqual(record.profile_hash, build_lot_scoring_profile_hash(normalized_profile))
        self.assertTrue(record.is_active)

    async def test_save_profile_persists_and_refreshes(self) -> None:
        session = FakeSession()
        payload = {"profile_identifier": "profile-1", "target_regions": ["Москва"]}

        profile = await scoring_profile_store_service.save_profile(session, "Main profile", payload, is_active=True)

        self.assertEqual(len(session.added), 1)
        self.assertEqual(session.commits, 1)
        self.assertEqual(len(session.refreshed), 1)
        self.assertIs(session.added[0], profile)
        self.assertTrue(profile.is_active)
        self.assertEqual(profile.profile_payload["target_regions"], ["Москва"])
        self.assertEqual(profile.profile_hash, build_lot_scoring_profile_hash(LotScoringProfile.model_validate(profile.profile_payload)))

        record = make_record()
        detail_cache = make_detail_cache()
        work_item = make_work_item()
        baseline_rating = recalculate_record_rating(record, detail_cache, work_item)
        no_profile_rating = recalculate_record_rating(record, detail_cache, work_item, scoring_profile=None)

        self.assertEqual(baseline_rating.score, no_profile_rating.score)
        self.assertEqual(baseline_rating.input_hash, no_profile_rating.input_hash)

    async def test_get_active_profile_returns_latest_active_profile(self) -> None:
        active_profile = scoring_profile_store_service.build_profile_record(
            "Active",
            {"profile_identifier": "active-1", "target_regions": ["Москва"]},
            is_active=True,
        )
        session = FakeSession(scalar_result=active_profile)

        fetched = await scoring_profile_store_service.get_active_profile(session)

        self.assertIs(fetched, active_profile)
        statement = session.statements[0]
        sql = str(statement.compile(dialect=postgresql.dialect()))
        self.assertIn("scoring_profiles.is_active IS true", sql)
        self.assertIn("scoring_profiles.updated_at DESC", sql)

    def test_invalid_profile_payload_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            scoring_profile_store_service.normalize_profile_payload({"strategy": "invalid"})


if __name__ == "__main__":
    unittest.main()
