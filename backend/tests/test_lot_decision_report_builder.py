from __future__ import annotations

import unittest
from decimal import Decimal

from app.models.auction import AuctionLotDetailCache, AuctionLotRecord, AuctionLotWorkItem
from app.schemas.auctions import LotDatagridRow, LotFreshness, LotRating
from app.schemas.lot_decision_report import ActionRecommendation, DecisionLevel
from app.schemas.scoring_profile import LotScoringProfile, build_lot_scoring_profile_hash
from app.services.lot_decision_report import build_lot_decision_report


def make_record(
    *,
    lot_name: str = "Tracked excavator",
    score: int = 80,
    level: str = "high",
    status: str = "Accepting applications",
    score_breakdown: dict | None = None,
) -> AuctionLotRecord:
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
        current_price="1000000 RUB",
        current_price_value=Decimal("1000000"),
        location_region="Moscow Oblast",
        application_deadline="31.12.2026 18:00",
        freshness=LotFreshness(is_new=True),
        rating=LotRating(score=score, level=level, reasons=[]),
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
        initial_price="1000000 RUB",
        content_hash="content-hash",
        rating_score=score,
        rating_level=level,
        score_breakdown=score_breakdown
        if score_breakdown is not None
        else {
            "reasons": ["Price recognized", "Operationally ready"],
            "caps": [],
            "inputs": {},
        },
        datagrid_row=row.model_dump(mode="json"),
        normalized_item={
            "auction": {"application_deadline": "31.12.2026 18:00"},
            "lot": {
                "category": "Special equipment",
                "region": "Moscow Oblast",
                "current_price": "1000000 RUB",
            },
        },
    )


def make_detail_cache(*, documents: list[dict] | None = None) -> AuctionLotDetailCache:
    return AuctionLotDetailCache(
        lot_record_id=1,
        content_hash="detail-hash",
        lot_detail={
            "lot": {
                "description": "Local detail payload",
                "inspection_order": "By appointment",
            }
        },
        auction_detail=None,
        documents=documents if documents is not None else [{"name": "documents.pdf"}],
    )


class LotDecisionReportBuilderTests(unittest.TestCase):
    def test_low_score_becomes_ignore(self) -> None:
        report = build_lot_decision_report(
            make_record(score=30, level="low"),
            detail_cache=make_detail_cache(),
        )

        self.assertEqual(report.decision_level, DecisionLevel.IGNORE)
        self.assertEqual(report.recommendation, ActionRecommendation.IGNORE)

    def test_high_score_becomes_inspect_or_calculate_without_profile_match(self) -> None:
        report = build_lot_decision_report(
            make_record(score=88, level="high"),
            detail_cache=make_detail_cache(),
        )

        self.assertIn(report.decision_level, {DecisionLevel.INSPECT, DecisionLevel.CALCULATE})
        self.assertIn(
            report.recommendation,
            {ActionRecommendation.INSPECT, ActionRecommendation.CALCULATE_MAX_BID},
        )

    def test_missing_documents_adds_request_docs_action(self) -> None:
        report = build_lot_decision_report(
            make_record(score=72, level="high"),
            detail_cache=make_detail_cache(documents=[]),
        )

        self.assertEqual(report.recommendation, ActionRecommendation.REQUEST_DOCS)
        self.assertIn(
            ActionRecommendation.REQUEST_DOCS,
            {action.action for action in report.next_actions},
        )
        self.assertIn("Запросить документы", {action.label for action in report.next_actions})

    def test_profile_blocker_downgrades_decision(self) -> None:
        record = make_record(lot_name="Blocked tracked excavator", score=92, level="high")
        profile = LotScoringProfile(
            profile_identifier="profile-1",
            target_regions=["Moscow Oblast"],
            target_categories=["Special equipment"],
            stop_words=["blocked"],
        )

        report = build_lot_decision_report(
            record,
            detail_cache=make_detail_cache(),
            profile=profile,
        )

        self.assertEqual(report.decision_level, DecisionLevel.WATCH)
        self.assertNotEqual(report.decision_level, DecisionLevel.BID_CANDIDATE)
        self.assertEqual(report.profile_hash, build_lot_scoring_profile_hash(profile))
        self.assertTrue(any(risk.code == "profile.blocker" for risk in report.risks))

    def test_high_score_with_profile_match_becomes_bid_candidate(self) -> None:
        profile = LotScoringProfile(
            profile_identifier="profile-1",
            target_regions=["Moscow Oblast"],
            target_categories=["Special equipment"],
        )

        report = build_lot_decision_report(
            make_record(score=92, level="high"),
            detail_cache=make_detail_cache(),
            work_item=AuctionLotWorkItem(lot_record_id=1, max_purchase_price=Decimal("1200000")),
            profile=profile,
        )

        self.assertEqual(report.decision_level, DecisionLevel.BID_CANDIDATE)
        self.assertEqual(report.recommendation, ActionRecommendation.PREPARE_BID)


if __name__ == "__main__":
    unittest.main()
