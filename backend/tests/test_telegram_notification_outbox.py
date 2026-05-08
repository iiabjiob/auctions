from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.models.auction import AuctionLotDecisionReport, TelegramNotificationOutbox
from app.schemas.lot_decision_report import (
    ActionRecommendation,
    DecisionLevel,
    LotDecisionReason,
    LotDecisionReport,
    LotEconomicsDecision,
    TelegramNotificationStatus,
)
from app.services.lot_decision_report import (
    build_lot_decision_report_snapshot_hash,
    enqueue_lot_telegram_notification_outbox,
    evaluate_lot_notification_eligibility,
)


GENERATED_AT = datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc)


class FakeSession:
    def __init__(self, scalar_results: list[object | None] | None = None) -> None:
        self.scalar_results = list(scalar_results or [])
        self.statements = []
        self.added: list[object] = []
        self.flushes = 0

    async def scalar(self, statement):  # noqa: ANN001
        self.statements.append(statement)
        if self.scalar_results:
            return self.scalar_results.pop(0)
        return None

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        self.flushes += 1


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


def make_snapshot(report: LotDecisionReport) -> AuctionLotDecisionReport:
    return AuctionLotDecisionReport(
        id=10,
        lot_record_id=report.record_id,
        profile_hash=report.profile_hash,
        report_payload=report.model_dump(mode="json"),
        decision_level=report.decision_level.value,
        recommendation=report.recommendation.value,
        notification_should_send=evaluate_lot_notification_eligibility(report).should_notify,
        report_hash=build_lot_decision_report_snapshot_hash(report),
        generated_at=report.generated_at,
    )


def make_outbox_entry(report: LotDecisionReport, *, status: TelegramNotificationStatus) -> TelegramNotificationOutbox:
    eligibility = evaluate_lot_notification_eligibility(report)
    return TelegramNotificationOutbox(
        lot_record_id=report.record_id,
        decision_report_id=10,
        dedupe_key=eligibility.dedupe_key,
        cooldown_key=eligibility.cooldown_key,
        status=status.value,
        priority=eligibility.priority,
        message_payload={"text": "existing", "parse_mode": "HTML"},
        report_hash=build_lot_decision_report_snapshot_hash(report),
        scheduled_at=GENERATED_AT,
        cooldown_until=GENERATED_AT + timedelta(hours=1),
    )


class TelegramNotificationOutboxTests(unittest.IsolatedAsyncioTestCase):
    def test_status_values_are_stable(self) -> None:
        self.assertEqual(TelegramNotificationStatus.PENDING.value, "pending")
        self.assertEqual(TelegramNotificationStatus.SENT.value, "sent")
        self.assertEqual(TelegramNotificationStatus.FAILED.value, "failed")
        self.assertEqual(TelegramNotificationStatus.SKIPPED.value, "skipped")

    async def test_eligible_report_enqueues_pending_notification(self) -> None:
        report = make_report()
        session = FakeSession([None, None])

        entry = await enqueue_lot_telegram_notification_outbox(
            session,
            make_snapshot(report),
            report=report,
            now=GENERATED_AT,
            cooldown_seconds=3600,
        )

        eligibility = evaluate_lot_notification_eligibility(report)
        self.assertIs(entry, session.added[0])
        self.assertEqual(session.flushes, 1)
        self.assertEqual(entry.status, "pending")
        self.assertEqual(entry.dedupe_key, eligibility.dedupe_key)
        self.assertEqual(entry.cooldown_key, eligibility.cooldown_key)
        self.assertEqual(entry.cooldown_until, GENERATED_AT + timedelta(hours=1))
        self.assertIn("Tracked excavator", entry.message_payload["text"])

    async def test_ineligible_report_does_not_enqueue(self) -> None:
        report = make_report(
            rating_score=30,
            rating_level="low",
            decision_level=DecisionLevel.IGNORE,
            recommendation=ActionRecommendation.IGNORE,
            profile_hash=None,
            profile_fit_summary=None,
        )
        session = FakeSession()

        entry = await enqueue_lot_telegram_notification_outbox(
            session,
            make_snapshot(report),
            report=report,
            now=GENERATED_AT,
        )

        self.assertIsNone(entry)
        self.assertEqual(session.added, [])
        self.assertEqual(session.flushes, 0)

    async def test_existing_dedupe_key_is_returned_without_duplicate_insert(self) -> None:
        report = make_report()
        existing = make_outbox_entry(report, status=TelegramNotificationStatus.PENDING)
        session = FakeSession([existing])

        entry = await enqueue_lot_telegram_notification_outbox(
            session,
            make_snapshot(report),
            report=report,
            now=GENERATED_AT,
        )

        self.assertIs(entry, existing)
        self.assertEqual(session.added, [])
        self.assertEqual(session.flushes, 0)
        self.assertEqual(len(session.statements), 1)

    async def test_active_cooldown_inserts_skipped_notification(self) -> None:
        first_report = make_report()
        changed_report = make_report(rating_score=88)
        active_cooldown = make_outbox_entry(first_report, status=TelegramNotificationStatus.PENDING)
        session = FakeSession([None, active_cooldown])

        entry = await enqueue_lot_telegram_notification_outbox(
            session,
            make_snapshot(changed_report),
            report=changed_report,
            now=GENERATED_AT,
            cooldown_seconds=3600,
        )

        self.assertIs(entry, session.added[0])
        self.assertEqual(entry.status, "skipped")
        self.assertEqual(entry.cooldown_key, active_cooldown.cooldown_key)
        self.assertEqual(entry.cooldown_until, active_cooldown.cooldown_until)
        self.assertNotEqual(entry.dedupe_key, active_cooldown.dedupe_key)
        self.assertEqual(session.flushes, 1)


if __name__ == "__main__":
    unittest.main()
