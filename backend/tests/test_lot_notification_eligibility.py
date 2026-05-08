from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.schemas.lot_decision_report import (
    ActionRecommendation,
    DecisionLevel,
    LotDecisionReason,
    LotDecisionReport,
    LotDecisionRisk,
    LotEconomicsDecision,
)
from app.services.lot_decision_report import evaluate_lot_notification_eligibility


GENERATED_AT = datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc)


def make_report(**overrides: object) -> LotDecisionReport:
    values = {
        "source": "tbankrot",
        "auction_id": "auction-1",
        "lot_id": "lot-1",
        "record_id": 1,
        "title": "Tracked excavator",
        "source_title": "TBankrot",
        "region": "Moscow Oblast",
        "current_price": "1000000 RUB",
        "deadline": (GENERATED_AT + timedelta(hours=48)).strftime("%d.%m.%Y %H:%M"),
        "rating_score": 92,
        "rating_level": "high",
        "profile_hash": "profile-hash",
        "profile_fit_summary": "Profile match",
        "economics": LotEconomicsDecision(
            current_price=Decimal("1000000"),
            market_value=Decimal("2200000"),
            expected_costs=Decimal("100000"),
            target_roi=Decimal("0.25"),
            max_buy_price=Decimal("1680000"),
            estimated_profit=Decimal("1100000"),
            confidence="high",
        ),
        "decision_level": DecisionLevel.BID_CANDIDATE,
        "recommendation": ActionRecommendation.PREPARE_BID,
        "reasons": (
            LotDecisionReason(code="score.reason.1", message="High score", source="score_breakdown"),
            LotDecisionReason(code="profile.match", message="Lot matches profile", source="profile_fit"),
        ),
        "risks": (),
        "next_actions": (),
        "generated_at": GENERATED_AT,
    }
    values.update(overrides)
    return LotDecisionReport(**values)


class LotNotificationEligibilityTests(unittest.TestCase):
    def test_high_quality_report_should_notify(self) -> None:
        eligibility = evaluate_lot_notification_eligibility(make_report())

        self.assertTrue(eligibility.should_notify)
        self.assertIn(eligibility.priority, {"high", "urgent"})
        self.assertIn("decision_level:bid_candidate", eligibility.reasons)
        self.assertIn("high_score", eligibility.reasons)
        self.assertEqual(eligibility.blockers, ())

    def test_low_score_report_should_not_notify(self) -> None:
        eligibility = evaluate_lot_notification_eligibility(
            make_report(
                rating_score=30,
                rating_level="low",
                decision_level=DecisionLevel.IGNORE,
                recommendation=ActionRecommendation.IGNORE,
                reasons=(LotDecisionReason(code="score.current", message="Low score", source="record"),),
                profile_hash=None,
                profile_fit_summary=None,
            )
        )

        self.assertFalse(eligibility.should_notify)
        self.assertEqual(eligibility.priority, "low")
        self.assertIn("decision_level_not_high", eligibility.blockers)

    def test_blocker_suppresses_notification(self) -> None:
        eligibility = evaluate_lot_notification_eligibility(
            make_report(
                risks=(
                    LotDecisionRisk(
                        code="profile.blocker",
                        message="Profile blocker present",
                        level="high",
                    ),
                )
            )
        )

        self.assertFalse(eligibility.should_notify)
        self.assertEqual(eligibility.priority, "low")
        self.assertIn("high_risk:profile.blocker", eligibility.blockers)

    def test_dedupe_key_is_deterministic(self) -> None:
        first = evaluate_lot_notification_eligibility(make_report())
        second = evaluate_lot_notification_eligibility(
            make_report(generated_at=GENERATED_AT + timedelta(minutes=15))
        )
        changed = evaluate_lot_notification_eligibility(make_report(rating_score=88))

        self.assertEqual(first.dedupe_key, second.dedupe_key)
        self.assertEqual(first.cooldown_key, second.cooldown_key)
        self.assertNotEqual(first.dedupe_key, changed.dedupe_key)
        self.assertEqual(first.cooldown_key, changed.cooldown_key)


if __name__ == "__main__":
    unittest.main()
