from __future__ import annotations

import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.auction import AuctionLotRecord
from app.schemas.analysis_config import ScoringDimensionWeights
from app.schemas.auctions import LotDatagridRow, LotFreshness, LotRating
from app.schemas.scoring_profile import LotScoringProfile
from app.worker import auction_analysis_worker


class FakeScalarResult:
    def __init__(self, values: list[object]) -> None:
        self._values = values

    def all(self) -> list[object]:
        return self._values


class FakeAnalysisSession:
    def __init__(self, *, scalar_batches: list[list[object]] | None = None) -> None:
        self.scalar_batches = list(scalar_batches or [])
        self.scalars_calls: list[object] = []
        self.scalar_calls: list[object] = []
        self.commit_count = 0

    async def scalars(self, statement):  # noqa: ANN001
        self.scalars_calls.append(statement)
        if self.scalar_batches:
            return FakeScalarResult(self.scalar_batches.pop(0))
        return FakeScalarResult([])

    async def scalar(self, statement):  # noqa: ANN001
        self.scalar_calls.append(statement)
        return None

    async def commit(self) -> None:
        self.commit_count += 1


class FakeSessionContext:
    def __init__(self, session: FakeAnalysisSession) -> None:
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return None


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
        lot_name="Экскаватор гусеничный",
        status="Идет прием заявок",
        initial_price="1 000 000 руб.",
        content_hash="hash",
        datagrid_row=row.model_dump(mode="json"),
        normalized_item={"auction": {"application_deadline": "05.05.2026 18:00"}, "lot": {"category": "Спецтехника"}},
    )


def make_runtime_config() -> SimpleNamespace:
    return SimpleNamespace(
        category_keywords={},
        exclusion_keywords=(),
        legal_risk_rules=None,
        owner_profile=None,
        dimension_weights=ScoringDimensionWeights(),
    )


class AuctionAnalysisWorkerProfileTests(unittest.IsolatedAsyncioTestCase):
    async def test_resolve_active_scoring_profile_is_disabled_by_default(self) -> None:
        session = FakeAnalysisSession()

        with patch.object(auction_analysis_worker.settings, "auction_analysis_use_active_scoring_profile", False), patch(
            "app.worker.auction_analysis_worker.scoring_profile_store_service.get_active_scoring_profile",
            AsyncMock(),
        ) as get_active_profile:
            profile, profile_hash = await auction_analysis_worker._resolve_active_scoring_profile(session)

        self.assertIsNone(profile)
        self.assertIsNone(profile_hash)
        get_active_profile.assert_not_awaited()

    async def test_resolve_active_scoring_profile_returns_active_profile_when_enabled(self) -> None:
        session = FakeAnalysisSession()
        active_profile = LotScoringProfile(profile_identifier="profile-1", target_regions=["Москва"])

        with patch.object(auction_analysis_worker.settings, "auction_analysis_use_active_scoring_profile", True), patch(
            "app.worker.auction_analysis_worker.scoring_profile_store_service.get_active_scoring_profile",
            AsyncMock(return_value=(active_profile, "profile-hash-1")),
        ) as get_active_profile:
            profile, profile_hash = await auction_analysis_worker._resolve_active_scoring_profile(session)

        self.assertEqual(profile, active_profile)
        self.assertEqual(profile_hash, "profile-hash-1")
        get_active_profile.assert_awaited_once_with(session)

    async def test_analyze_all_lots_uses_active_profile_when_enabled(self) -> None:
        record = make_record()
        session_one = FakeAnalysisSession(scalar_batches=[[record.id]])
        session_two = FakeAnalysisSession(scalar_batches=[[record], [], []])
        runtime_config = make_runtime_config()
        active_profile = LotScoringProfile(profile_identifier="profile-1", target_regions=["Москва"])
        captured_hash_kwargs: list[dict[str, object]] = []

        def fake_build_hash(record_arg, detail_cache_arg, work_item_arg, **kwargs):  # noqa: ANN001
            captured_hash_kwargs.append(kwargs)
            return "stale-hash"

        fake_recalculate = MagicMock(return_value=SimpleNamespace())

        with (
            patch.object(auction_analysis_worker.settings, "auction_analysis_use_active_scoring_profile", True),
            patch("app.worker.auction_analysis_worker.AsyncSessionLocal", side_effect=[FakeSessionContext(session_one), FakeSessionContext(session_two)]),
            patch("app.worker.auction_analysis_worker.auction_analysis_config_service.get_runtime_config", AsyncMock(return_value=runtime_config)),
            patch("app.worker.auction_analysis_worker.scoring_profile_store_service.get_active_scoring_profile", AsyncMock(return_value=(active_profile, "profile-hash-1"))),
            patch("app.worker.auction_analysis_worker.build_record_score_input_hash", side_effect=fake_build_hash),
            patch("app.worker.auction_analysis_worker.recalculate_record_rating", new=fake_recalculate),
            patch("app.worker.auction_analysis_worker.record_score_is_current", return_value=False),
            patch("app.worker.auction_analysis_worker.bump_auction_lot_dataset_version", AsyncMock()) as bump_dataset_version,
        ):
            result = await auction_analysis_worker.analyze_all_lots(limit=1)

        self.assertEqual(result["processed"], 1)
        self.assertEqual(result["unchanged"], 1)
        self.assertEqual(len(captured_hash_kwargs), 1)
        self.assertEqual(captured_hash_kwargs[0]["scoring_profile"], active_profile)
        self.assertEqual(captured_hash_kwargs[0]["profile_hash"], "profile-hash-1")
        self.assertEqual(fake_recalculate.call_count, 1)
        self.assertEqual(fake_recalculate.call_args.kwargs["scoring_profile"], active_profile)
        self.assertEqual(fake_recalculate.call_args.kwargs["profile_hash"], "profile-hash-1")
        bump_dataset_version.assert_not_awaited()

    async def test_analyze_all_lots_falls_back_when_active_profile_missing(self) -> None:
        record = make_record()
        session_one = FakeAnalysisSession(scalar_batches=[[record.id]])
        session_two = FakeAnalysisSession(scalar_batches=[[record], [], []])
        runtime_config = make_runtime_config()
        captured_hash_kwargs: list[dict[str, object]] = []

        def fake_build_hash(record_arg, detail_cache_arg, work_item_arg, **kwargs):  # noqa: ANN001
            captured_hash_kwargs.append(kwargs)
            return "stale-hash"

        fake_recalculate = MagicMock(return_value=SimpleNamespace())

        with (
            patch.object(auction_analysis_worker.settings, "auction_analysis_use_active_scoring_profile", True),
            patch("app.worker.auction_analysis_worker.AsyncSessionLocal", side_effect=[FakeSessionContext(session_one), FakeSessionContext(session_two)]),
            patch("app.worker.auction_analysis_worker.auction_analysis_config_service.get_runtime_config", AsyncMock(return_value=runtime_config)),
            patch("app.worker.auction_analysis_worker.scoring_profile_store_service.get_active_scoring_profile", AsyncMock(return_value=(None, None))),
            patch("app.worker.auction_analysis_worker.build_record_score_input_hash", side_effect=fake_build_hash),
            patch("app.worker.auction_analysis_worker.recalculate_record_rating", new=fake_recalculate),
            patch("app.worker.auction_analysis_worker.record_score_is_current", return_value=False),
        ):
            result = await auction_analysis_worker.analyze_all_lots(limit=1)

        self.assertEqual(result["processed"], 1)
        self.assertEqual(len(captured_hash_kwargs), 1)
        self.assertNotIn("scoring_profile", captured_hash_kwargs[0])
        self.assertNotIn("profile_hash", captured_hash_kwargs[0])
        self.assertEqual(fake_recalculate.call_count, 1)
        self.assertNotIn("scoring_profile", fake_recalculate.call_args.kwargs)
        self.assertNotIn("profile_hash", fake_recalculate.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()
