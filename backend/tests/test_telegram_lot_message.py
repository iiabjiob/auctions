from __future__ import annotations

import unittest
from datetime import datetime, timezone
from decimal import Decimal

from app.schemas.lot_decision_report import (
    ActionRecommendation,
    DecisionLevel,
    LotDecisionReason,
    LotDecisionReport,
    LotDecisionRisk,
    LotEconomicsDecision,
)
from app.services.lot_decision_report import TELEGRAM_MAX_MESSAGE_LENGTH, render_telegram_lot_message


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
        "deadline": "10.05.2026 18:00",
        "rating_score": 92,
        "rating_level": "high",
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
            LotDecisionReason(code="profile.match", message="Profile match", source="profile_fit"),
        ),
        "risks": (
            LotDecisionRisk(code="documents.review", message="Review documents", level="medium"),
        ),
        "next_actions": (),
        "generated_at": GENERATED_AT,
    }
    values.update(overrides)
    return LotDecisionReport(**values)


class TelegramLotMessageTests(unittest.TestCase):
    def test_message_contains_required_fields(self) -> None:
        message = render_telegram_lot_message(make_report(), link="https://app.test/lots/1")

        self.assertIn("<b>Tracked excavator</b>", message.text)
        self.assertIn("Region: Moscow Oblast", message.text)
        self.assertIn("Price: 1000000 RUB", message.text)
        self.assertIn("Score: 92 (high)", message.text)
        self.assertIn("Decision: bid_candidate / prepare_bid", message.text)
        self.assertIn("Max buy: 1680000", message.text)
        self.assertIn("Deadline: 10.05.2026 18:00", message.text)
        self.assertIn("Reasons:", message.text)
        self.assertIn("- High score", message.text)
        self.assertIn("Risks:", message.text)
        self.assertIn("- Review documents", message.text)
        self.assertIn("Link: https://app.test/lots/1", message.text)
        self.assertEqual(message.message_length, len(message.text))

    def test_message_escapes_html(self) -> None:
        message = render_telegram_lot_message(
            make_report(title="Loader <special>", reasons=(LotDecisionReason(code="x", message="A < B", source=None),))
        )

        self.assertIn("<b>Loader &lt;special&gt;</b>", message.text)
        self.assertIn("- A &lt; B", message.text)

    def test_message_length_is_bounded(self) -> None:
        long_reason = "Long reason " * 1000
        message = render_telegram_lot_message(
            make_report(reasons=(LotDecisionReason(code="long", message=long_reason, source=None),)),
            max_length=500,
        )

        self.assertLessEqual(message.message_length, 500)
        self.assertTrue(message.text.endswith("..."))

    def test_default_length_limit_is_telegram_safe(self) -> None:
        long_reason = "Long reason " * 1000
        message = render_telegram_lot_message(
            make_report(reasons=(LotDecisionReason(code="long", message=long_reason, source=None),))
        )

        self.assertLessEqual(message.message_length, TELEGRAM_MAX_MESSAGE_LENGTH)


if __name__ == "__main__":
    unittest.main()
