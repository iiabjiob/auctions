from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from app.models import UserInterestProfileModel, UserTelegramBindingModel
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
    enqueue_user_scoped_lot_telegram_notifications,
    evaluate_lot_notification_eligibility,
    generate_and_persist_lot_decision_report_snapshot,
)
from tests.test_lot_evidence import make_detail_cache, make_record


GENERATED_AT = datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc)


class FakeSession:
    def __init__(
        self,
        scalar_results: list[object | None] | None = None,
        scalars_result: list[object] | None = None,
        scalars_results: list[list[object]] | None = None,
    ) -> None:
        self.scalar_results = list(scalar_results or [])
        self.scalars_result = list(scalars_result or [])
        self.scalars_results = list(scalars_results or [])
        self.statements = []
        self.scalars_statements = []
        self.added: list[object] = []
        self.flushes = 0

    async def scalar(self, statement):  # noqa: ANN001
        self.statements.append(statement)
        if self.scalar_results:
            return self.scalar_results.pop(0)
        return None

    async def scalars(self, statement):  # noqa: ANN001
        self.scalars_statements.append(statement)
        if self.scalars_results:
            return FakeScalars(self.scalars_results.pop(0))
        return FakeScalars(self.scalars_result)

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        self.flushes += 1


class FakeScalars:
    def __init__(self, values: list[object]) -> None:
        self.values = values

    def all(self) -> list[object]:
        return self.values


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


def make_interest_profile(**overrides: object) -> UserInterestProfileModel:
    values = {
        "id": "uip_1",
        "owner_user_id": "user-1",
        "name": "Special machinery",
        "profile_payload": {
            "target_categories": ["Спецтехника"],
            "budget_min": "800000",
        },
        "min_rating": 80,
        "notification_priority_threshold": "medium",
        "telegram_enabled": True,
        "is_active": True,
    }
    values.update(overrides)
    return UserInterestProfileModel(**values)


def make_telegram_binding(**overrides: object) -> UserTelegramBindingModel:
    values = {
        "user_id": "user-1",
        "telegram_chat_id": "123456789",
        "username": "auction_user",
    }
    values.update(overrides)
    return UserTelegramBindingModel(**values)


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
        self.assertIsNone(entry.user_id)
        self.assertIsNone(entry.telegram_chat_id)
        self.assertIsNone(entry.interest_profile_id)
        self.assertEqual(entry.cooldown_until, GENERATED_AT + timedelta(hours=1))
        self.assertIn("Tracked excavator", entry.message_payload["text"])

    def test_user_scoped_fields_are_optional_for_backward_compatibility(self) -> None:
        report = make_report()
        global_entry = make_outbox_entry(report, status=TelegramNotificationStatus.PENDING)
        user_entry = make_outbox_entry(report, status=TelegramNotificationStatus.PENDING)
        user_entry.user_id = "user-1"
        user_entry.telegram_chat_id = "123456789"
        user_entry.interest_profile_id = "uip_1"

        self.assertIsNone(global_entry.user_id)
        self.assertIsNone(global_entry.telegram_chat_id)
        self.assertIsNone(global_entry.interest_profile_id)
        self.assertEqual(user_entry.user_id, "user-1")
        self.assertEqual(user_entry.telegram_chat_id, "123456789")
        self.assertEqual(user_entry.interest_profile_id, "uip_1")

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

    async def test_user_scoped_enqueue_inserts_for_matching_profile_only(self) -> None:
        record = make_record()
        record.rating_score = 92
        report = make_report(record_id=record.id)
        matching = make_interest_profile(id="uip_match", owner_user_id="user-1")
        non_matching = make_interest_profile(
            id="uip_bmw",
            owner_user_id="user-2",
            profile_payload={"target_categories": ["Автомобили"], "desired_keywords": ["BMW"]},
            min_rating=80,
        )
        session = FakeSession(
            scalar_results=[None, None, None],
            scalars_results=[[matching, non_matching], [make_telegram_binding(user_id="user-1")]],
        )

        entries = await enqueue_user_scoped_lot_telegram_notifications(
            session,
            make_snapshot(report),
            record,
            detail_cache=make_detail_cache(),
            report=report,
            now=GENERATED_AT,
            cooldown_seconds=3600,
        )

        self.assertEqual(entries, session.added)
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual(entry.user_id, "user-1")
        self.assertEqual(entry.interest_profile_id, "uip_match")
        self.assertEqual(entry.telegram_chat_id, "123456789")
        self.assertEqual(entry.status, "pending")
        self.assertEqual(entry.dedupe_key, f"telegram:user-1:uip_match:{record.id}:{make_snapshot(report).report_hash}")
        self.assertEqual(entry.cooldown_key, f"telegram:user-1:uip_match:{record.id}")
        self.assertEqual(entry.cooldown_until, GENERATED_AT + timedelta(hours=1))
        self.assertEqual(session.flushes, 1)

    async def test_user_scoped_enqueue_uses_profile_match_for_watch_rating(self) -> None:
        record = make_record()
        record.rating_score = 55
        report = make_report(
            record_id=record.id,
            rating_score=55,
            rating_level="medium",
            decision_level=DecisionLevel.WATCH,
            recommendation=ActionRecommendation.MONITOR,
        )
        profile = make_interest_profile(id="uip_transport", owner_user_id="user-1", min_rating=50)
        session = FakeSession(
            scalar_results=[None, None, None],
            scalars_results=[[profile], [make_telegram_binding(user_id="user-1")]],
        )

        entries = await enqueue_user_scoped_lot_telegram_notifications(
            session,
            make_snapshot(report),
            record,
            detail_cache=make_detail_cache(),
            report=report,
            now=GENERATED_AT,
            cooldown_seconds=3600,
        )

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].status, "pending")
        self.assertEqual(entries[0].priority, "urgent")
        self.assertEqual(entries[0].interest_profile_id, "uip_transport")
        self.assertEqual(session.flushes, 1)

    async def test_user_scoped_enqueue_allows_same_lot_for_two_users(self) -> None:
        record = make_record()
        record.rating_score = 92
        report = make_report(record_id=record.id)
        first = make_interest_profile(id="uip_1", owner_user_id="user-1")
        second = make_interest_profile(id="uip_2", owner_user_id="user-2")
        session = FakeSession(
            scalar_results=[None, None, None, None, None, None],
            scalars_results=[
                [first, second],
                [
                    make_telegram_binding(user_id="user-1", telegram_chat_id="111"),
                    make_telegram_binding(user_id="user-2", telegram_chat_id="222"),
                ],
            ],
        )

        entries = await enqueue_user_scoped_lot_telegram_notifications(
            session,
            make_snapshot(report),
            record,
            detail_cache=make_detail_cache(),
            report=report,
            now=GENERATED_AT,
        )

        self.assertEqual(len(entries), 2)
        self.assertEqual({entry.user_id for entry in entries}, {"user-1", "user-2"})
        self.assertEqual({entry.telegram_chat_id for entry in entries}, {"111", "222"})
        self.assertEqual(len({entry.dedupe_key for entry in entries}), 2)
        self.assertEqual(len({entry.cooldown_key for entry in entries}), 2)
        self.assertEqual(session.flushes, 1)

    async def test_user_scoped_enqueue_skips_same_lot_for_same_user_across_profiles(self) -> None:
        record = make_record()
        record.rating_score = 92
        report = make_report(record_id=record.id)
        first = make_interest_profile(id="uip_1", owner_user_id="user-1")
        second = make_interest_profile(id="uip_2", owner_user_id="user-1")
        session = FakeSession(
            scalar_results=[None, None, None],
            scalars_results=[[first, second], [make_telegram_binding(user_id="user-1")]],
        )

        entries = await enqueue_user_scoped_lot_telegram_notifications(
            session,
            make_snapshot(report),
            record,
            detail_cache=make_detail_cache(),
            report=report,
            now=GENERATED_AT,
        )

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].user_id, "user-1")
        self.assertEqual(entries[0].interest_profile_id, "uip_1")
        self.assertEqual(session.flushes, 1)

    async def test_user_scoped_enqueue_returns_existing_user_lot_delivery_without_duplicate_insert(self) -> None:
        record = make_record()
        record.rating_score = 92
        report = make_report(record_id=record.id)
        profile = make_interest_profile(id="uip_2", owner_user_id="user-1")
        existing = make_outbox_entry(report, status=TelegramNotificationStatus.SENT)
        existing.user_id = "user-1"
        existing.interest_profile_id = "uip_1"
        existing.dedupe_key = f"telegram:user-1:uip_1:{record.id}:old-report-hash"
        existing.cooldown_key = f"telegram:user-1:uip_1:{record.id}"
        session = FakeSession(scalar_results=[existing], scalars_results=[[profile], [make_telegram_binding()]])

        entries = await enqueue_user_scoped_lot_telegram_notifications(
            session,
            make_snapshot(report),
            record,
            detail_cache=make_detail_cache(),
            report=report,
            now=GENERATED_AT,
        )

        self.assertEqual(entries, [existing])
        self.assertEqual(session.added, [])
        self.assertEqual(session.flushes, 0)

    async def test_user_scoped_enqueue_returns_existing_entry_without_duplicate_insert(self) -> None:
        record = make_record()
        record.rating_score = 92
        report = make_report(record_id=record.id)
        snapshot = make_snapshot(report)
        profile = make_interest_profile(id="uip_1", owner_user_id="user-1")
        existing = make_outbox_entry(report, status=TelegramNotificationStatus.PENDING)
        existing.user_id = "user-1"
        existing.interest_profile_id = "uip_1"
        existing.dedupe_key = f"telegram:user-1:uip_1:{record.id}:{snapshot.report_hash}"
        existing.cooldown_key = f"telegram:user-1:uip_1:{record.id}"
        session = FakeSession(scalar_results=[existing], scalars_results=[[profile], [make_telegram_binding()]])

        entries = await enqueue_user_scoped_lot_telegram_notifications(
            session,
            snapshot,
            record,
            detail_cache=make_detail_cache(),
            report=report,
            now=GENERATED_AT,
        )

        self.assertEqual(entries, [existing])
        self.assertEqual(session.added, [])
        self.assertEqual(session.flushes, 0)

    async def test_user_scoped_enqueue_skips_when_no_profile_matches(self) -> None:
        record = make_record()
        record.rating_score = 92
        report = make_report(record_id=record.id)
        profile = make_interest_profile(
            id="uip_bmw",
            owner_user_id="user-1",
            profile_payload={"target_categories": ["Автомобили"], "desired_keywords": ["BMW"]},
            min_rating=80,
        )
        session = FakeSession(scalars_results=[[profile], []])

        entries = await enqueue_user_scoped_lot_telegram_notifications(
            session,
            make_snapshot(report),
            record,
            detail_cache=make_detail_cache(),
            report=report,
            now=GENERATED_AT,
        )

        self.assertEqual(entries, [])
        self.assertEqual(session.added, [])
        self.assertEqual(session.flushes, 0)

    async def test_generate_snapshot_flow_invokes_user_scoped_enqueue(self) -> None:
        record = make_record()
        record.rating_score = 92
        record.rating_level = "high"
        snapshot = make_snapshot(make_report(record_id=record.id))
        session = FakeSession()

        with (
            patch(
                "app.services.lot_decision_report.upsert_lot_decision_report_snapshot",
                AsyncMock(return_value=snapshot),
            ) as upsert_snapshot,
            patch(
                "app.services.lot_decision_report.enqueue_lot_telegram_notification_outbox",
                AsyncMock(return_value=None),
            ) as enqueue_global,
            patch(
                "app.services.lot_decision_report.enqueue_user_scoped_lot_telegram_notifications",
                AsyncMock(return_value=[]),
            ) as enqueue_user_scoped,
        ):
            result = await generate_and_persist_lot_decision_report_snapshot(
                session,
                record,
                make_detail_cache(),
                None,
            )

        self.assertIs(result, snapshot)
        upsert_snapshot.assert_awaited_once()
        enqueue_global.assert_awaited_once()
        enqueue_user_scoped.assert_awaited_once()
        self.assertIs(enqueue_user_scoped.await_args.args[2], record)


if __name__ == "__main__":
    unittest.main()
