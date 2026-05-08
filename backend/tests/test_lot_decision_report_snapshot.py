from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.models.auction import AuctionLotDecisionReport
from app.schemas.lot_decision_report import (
    ActionRecommendation,
    DecisionLevel,
    LotDecisionReason,
    LotDecisionReport,
    LotEconomicsDecision,
)
from app.services.lot_decision_report import (
    build_lot_decision_report_snapshot_hash,
    upsert_lot_decision_report_snapshot,
)


GENERATED_AT = datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc)


class FakeSession:
    def __init__(self, scalar_result: AuctionLotDecisionReport | None = None) -> None:
        self.scalar_result = scalar_result
        self.statements = []
        self.added: list[object] = []
        self.flushes = 0

    async def scalar(self, statement):  # noqa: ANN001
        self.statements.append(statement)
        return self.scalar_result

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


class LotDecisionReportSnapshotTests(unittest.IsolatedAsyncioTestCase):
    async def test_report_snapshot_is_created(self) -> None:
        session = FakeSession()
        report = make_report()

        snapshot = await upsert_lot_decision_report_snapshot(session, report)

        self.assertEqual(len(session.added), 1)
        self.assertIs(session.added[0], snapshot)
        self.assertEqual(session.flushes, 1)
        self.assertEqual(snapshot.lot_record_id, 1)
        self.assertEqual(snapshot.profile_hash, "profile-hash")
        self.assertEqual(snapshot.decision_level, "bid_candidate")
        self.assertEqual(snapshot.recommendation, "prepare_bid")
        self.assertTrue(snapshot.notification_should_send)
        self.assertEqual(snapshot.report_payload["rating_score"], 92)
        self.assertEqual(snapshot.report_hash, build_lot_decision_report_snapshot_hash(report))

    async def test_existing_snapshot_is_updated(self) -> None:
        existing = AuctionLotDecisionReport(
            lot_record_id=1,
            profile_hash="profile-hash",
            report_payload={},
            decision_level="watch",
            recommendation="monitor",
            notification_should_send=False,
            report_hash="old-hash",
            generated_at=GENERATED_AT,
        )
        session = FakeSession(existing)

        snapshot = await upsert_lot_decision_report_snapshot(session, make_report(rating_score=88))

        self.assertIs(snapshot, existing)
        self.assertEqual(session.added, [])
        self.assertEqual(session.flushes, 1)
        self.assertEqual(snapshot.report_payload["rating_score"], 88)
        self.assertNotEqual(snapshot.report_hash, "old-hash")

    def test_unchanged_report_hash_is_stable(self) -> None:
        first = make_report()
        second = make_report(generated_at=GENERATED_AT + timedelta(minutes=5))

        self.assertEqual(
            build_lot_decision_report_snapshot_hash(first),
            build_lot_decision_report_snapshot_hash(second),
        )

    def test_changed_score_or_evidence_changes_report_hash(self) -> None:
        baseline = make_report()
        changed_score = make_report(rating_score=88)
        changed_evidence = make_report(current_price="900000 RUB")

        self.assertNotEqual(
            build_lot_decision_report_snapshot_hash(baseline),
            build_lot_decision_report_snapshot_hash(changed_score),
        )
        self.assertNotEqual(
            build_lot_decision_report_snapshot_hash(baseline),
            build_lot_decision_report_snapshot_hash(changed_evidence),
        )


if __name__ == "__main__":
    unittest.main()
