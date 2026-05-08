from __future__ import annotations

import unittest
from datetime import datetime, timezone

from app.schemas.lot_decision_report import (
    ActionRecommendation,
    DecisionLevel,
    LotDecisionNextAction,
    LotDecisionReason,
    LotDecisionReport,
    LotDecisionRisk,
    build_lot_decision_report_hash,
    lot_decision_report_canonical_json,
)


def make_report(**overrides: object) -> LotDecisionReport:
    values = {
        "source": "tbankrot",
        "auction_id": "auction-1",
        "lot_id": "lot-1",
        "record_id": 1,
        "title": "Tracked excavator",
        "source_title": "TBankrot",
        "region": "Moscow Oblast",
        "current_price": "900000 RUB",
        "deadline": "05.05.2026 18:00",
        "rating_score": 82,
        "rating_level": "high",
        "decision_level": DecisionLevel.INSPECT,
        "recommendation": ActionRecommendation.INSPECT,
        "reasons": (
            LotDecisionReason(
                code="score.high",
                message="High rating",
                source="score_breakdown",
            ),
            LotDecisionReason(
                code="profile.region",
                message="Region matches profile",
                source="profile_fit",
            ),
        ),
        "risks": (
            LotDecisionRisk(
                code="documents.missing",
                message="Documents need review",
                level="medium",
            ),
        ),
        "next_actions": (
            LotDecisionNextAction(
                action=ActionRecommendation.REQUEST_DOCS,
                label="Request documents",
            ),
            LotDecisionNextAction(
                action=ActionRecommendation.INSPECT,
                label="Schedule inspection",
            ),
        ),
        "generated_at": datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc),
    }
    values.update(overrides)
    return LotDecisionReport(**values)


class LotDecisionReportTests(unittest.TestCase):
    def test_minimal_valid_report_can_be_created(self) -> None:
        report = LotDecisionReport(
            source="tbankrot",
            auction_id="auction-1",
            lot_id="lot-1",
            record_id=1,
            rating_score=0,
            rating_level="low",
            decision_level=DecisionLevel.WATCH,
            recommendation=ActionRecommendation.MONITOR,
            generated_at=datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(report.source, "tbankrot")
        self.assertEqual(report.decision_level, DecisionLevel.WATCH)
        self.assertEqual(report.reasons, ())
        self.assertEqual(report.risks, ())
        self.assertEqual(report.next_actions, ())

    def test_enum_values_are_stable(self) -> None:
        self.assertEqual(
            [value.value for value in DecisionLevel],
            ["ignore", "watch", "inspect", "calculate", "bid_candidate"],
        )
        self.assertEqual(
            [value.value for value in ActionRecommendation],
            [
                "ignore",
                "monitor",
                "request_docs",
                "inspect",
                "calculate_max_bid",
                "prepare_bid",
            ],
        )

    def test_serialization_and_hash_are_deterministic(self) -> None:
        first = make_report()
        second = make_report(
            reasons=tuple(reversed(first.reasons)),
            risks=first.risks,
            next_actions=first.next_actions,
        )
        third = make_report()

        self.assertEqual(first.canonical_payload(), third.canonical_payload())
        self.assertEqual(
            lot_decision_report_canonical_json(first),
            lot_decision_report_canonical_json(third),
        )
        self.assertEqual(
            build_lot_decision_report_hash(first),
            build_lot_decision_report_hash(third),
        )
        self.assertNotEqual(first.canonical_payload(), second.canonical_payload())
        self.assertNotEqual(
            lot_decision_report_canonical_json(first),
            lot_decision_report_canonical_json(second),
        )
        self.assertNotEqual(
            build_lot_decision_report_hash(first),
            build_lot_decision_report_hash(second),
        )

    def test_optional_profile_fields_can_be_omitted(self) -> None:
        report = make_report(profile_hash=None, profile_fit_summary=None)

        payload = report.canonical_payload()

        self.assertNotIn("profile_hash", payload)
        self.assertNotIn("profile_fit_summary", payload)


if __name__ == "__main__":
    unittest.main()
