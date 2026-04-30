from __future__ import annotations

import unittest
from datetime import UTC, datetime
from pathlib import Path

from app.services.auction_scoring import SCORING_VERSION
from app.services.auction_scoring_evaluation import build_scoring_regression_report, load_scoring_golden_cases


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "auction_scoring_golden_cases.json"


class AuctionScoringEvaluationTests(unittest.TestCase):
    def test_golden_fixture_set_covers_required_review_buckets(self) -> None:
        cases = load_scoring_golden_cases(FIXTURE_PATH)
        buckets = {case["review_bucket"] for case in cases}

        self.assertIn("known_excellent", buckets)
        self.assertIn("good_economics_high_risk", buckets)
        self.assertIn("excluded_category", buckets)
        self.assertIn("missing_data", buckets)
        self.assertIn("urgent", buckets)
        self.assertIn("manual_reject", buckets)
        self.assertIn("manual_watch", buckets)
        self.assertIn("manual_bid", buckets)

    def test_golden_fixture_regression_report_has_no_expectation_failures(self) -> None:
        cases = load_scoring_golden_cases(FIXTURE_PATH)
        report = build_scoring_regression_report(cases, now=datetime(2026, 4, 30, 12, 0, tzinfo=UTC))

        self.assertEqual(report["scoring_version"], SCORING_VERSION)
        self.assertEqual(report["summary"]["failed"], 0)
        self.assertEqual(report["failures"], [])

    def test_regression_report_compares_baseline_and_current_ranks(self) -> None:
        cases = load_scoring_golden_cases(FIXTURE_PATH)
        report = build_scoring_regression_report(cases, now=datetime(2026, 4, 30, 12, 0, tzinfo=UTC))
        ranking_by_id = {row["case_id"]: row for row in report["ranking"]}

        self.assertEqual(ranking_by_id["excellent_excavator"]["baseline_rank"], 1)
        self.assertIsInstance(ranking_by_id["excellent_excavator"]["current_rank"], int)
        self.assertIsInstance(ranking_by_id["excellent_excavator"]["rank_delta"], int)
        self.assertLess(
            ranking_by_id["excellent_excavator"]["current_rank"],
            ranking_by_id["excluded_apartment"]["current_rank"],
        )


if __name__ == "__main__":
    unittest.main()
