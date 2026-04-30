from __future__ import annotations

import unittest
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from app.models.auction import AuctionLotRecord, AuctionLotWorkItem
from app.schemas.auctions import LotDatagridRow, LotFreshness, LotRating
from app.services.auction_ai_ranking import (
    apply_operator_feedback,
    build_ai_candidates,
    compare_deterministic_and_ai_ranks,
    create_ai_analysis_record,
    is_deterministic_ai_candidate,
)
from app.services.auction_scoring_evaluation import build_scoring_regression_report, load_scoring_golden_cases


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "auction_scoring_golden_cases.json"


def make_record(record_id: int, *, score: int, level: str = "high") -> AuctionLotRecord:
    rating = LotRating(
        score=score,
        level=level,
        reasons=["fixture"],
        scoring_version="deterministic-v2",
        scored_at=datetime(2026, 4, 30, tzinfo=UTC),
        input_hash=f"hash-{record_id}",
        breakdown={"dimensions": {}, "caps": []},
    )
    row = LotDatagridRow(
        row_id=f"test:auction-{record_id}:lot-{record_id}",
        source="test",
        source_title="Test",
        auction_id=f"auction-{record_id}",
        lot_id=f"lot-{record_id}",
        lot_name=f"Lot {record_id}",
        status="Идет прием заявок",
        current_price="1000000 руб.",
        current_price_value=Decimal("1000000"),
        freshness=LotFreshness(is_new=False),
        rating=rating,
    )
    return AuctionLotRecord(
        id=record_id,
        source_code="test",
        auction_external_id=f"auction-{record_id}",
        lot_external_id=f"lot-{record_id}",
        lot_name=f"Lot {record_id}",
        status="Идет прием заявок",
        initial_price="1000000 руб.",
        content_hash=f"content-{record_id}",
        rating_score=score,
        rating_level=level,
        scoring_version="deterministic-v2",
        scored_at=datetime(2026, 4, 30, tzinfo=UTC),
        score_input_hash=f"hash-{record_id}",
        score_breakdown={"dimensions": {}, "caps": []},
        datagrid_row=row.model_dump(mode="json"),
        normalized_item={"lot": {"name": f"Lot {record_id}"}},
    )


class AuctionAiRankingTests(unittest.TestCase):
    def test_only_deterministic_shortlist_candidates_are_sent_to_ai(self) -> None:
        high_score = make_record(1, score=90)
        low_score = make_record(2, score=40, level="low")
        manual_watch = make_record(3, score=40, level="low")
        work_items = {3: AuctionLotWorkItem(lot_record_id=3, decision_status="watch")}

        candidates = build_ai_candidates([low_score, high_score, manual_watch], work_items=work_items)

        self.assertEqual([candidate.lot_record_id for candidate in candidates], [1, 3])
        self.assertTrue(is_deterministic_ai_candidate(high_score))
        self.assertFalse(is_deterministic_ai_candidate(low_score))

    def test_ai_analysis_record_keeps_deterministic_and_ai_scores_separate(self) -> None:
        candidate = build_ai_candidates([make_record(1, score=90)])[0]

        analysis = create_ai_analysis_record(
            candidate,
            model_version="ai-model-test",
            prompt_version="auction-rank-v1",
            ai_score=72,
            explanation="AI sees delivery risk.",
            confidence=Decimal("0.8200"),
            output_payload={"risk": "delivery"},
        )

        self.assertEqual(analysis.deterministic_score, 90)
        self.assertEqual(analysis.ai_score, 72)
        self.assertEqual(analysis.model_version, "ai-model-test")
        self.assertEqual(analysis.prompt_version, "auction-rank-v1")
        self.assertEqual(analysis.explanation, "AI sees delivery risk.")
        self.assertEqual(analysis.confidence, Decimal("0.8200"))

    def test_operator_feedback_fields_accept_supported_statuses(self) -> None:
        candidate = build_ai_candidates([make_record(1, score=90)])[0]
        analysis = create_ai_analysis_record(
            candidate,
            model_version="ai-model-test",
            prompt_version="auction-rank-v1",
            ai_score=88,
            explanation=None,
            confidence=None,
        )

        apply_operator_feedback(analysis, status="accepted", comment="Useful ranking", reviewer="operator")

        self.assertEqual(analysis.operator_feedback_status, "accepted")
        self.assertEqual(analysis.operator_feedback_comment, "Useful ranking")
        self.assertEqual(analysis.operator_feedback_by, "operator")
        self.assertIsNotNone(analysis.operator_feedback_at)

    def test_ai_rank_comparison_reports_rank_delta(self) -> None:
        candidates = build_ai_candidates([make_record(1, score=90), make_record(2, score=88)])

        comparison = compare_deterministic_and_ai_ranks(candidates, {1: 70, 2: 95})
        by_id = {row["lot_record_id"]: row for row in comparison}

        self.assertEqual(by_id[1]["deterministic_rank"], 1)
        self.assertEqual(by_id[1]["ai_rank"], 2)
        self.assertEqual(by_id[1]["rank_delta"], 1)
        self.assertEqual(by_id[2]["ai_rank"], 1)

    def test_evaluation_report_compares_deterministic_rank_vs_ai_rank(self) -> None:
        cases = load_scoring_golden_cases(FIXTURE_PATH)
        report = build_scoring_regression_report(
            cases,
            ai_scores={"excellent_excavator": 80, "urgent_loader": 95},
            now=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
        )

        comparison_by_id = {row["case_id"]: row for row in report["ai_rank_comparison"]}
        self.assertEqual(comparison_by_id["urgent_loader"]["ai_rank"], 1)
        self.assertIn("rank_delta", comparison_by_id["excellent_excavator"])


if __name__ == "__main__":
    unittest.main()
