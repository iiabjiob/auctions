from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.models.procurement import ProcurementLotRecord, ProcurementTelegramNotificationOutbox
from app.schemas.lot_decision_report import TelegramNotificationStatus
from app.services.procurement_notifications import (
    enqueue_procurement_telegram_notifications,
    evaluate_procurement_notification_events,
)


NOW = datetime(2026, 5, 13, 12, tzinfo=UTC)


class FakeSession:
    def __init__(self, existing: object | None = None) -> None:
        self.existing = existing
        self.added: list[object] = []
        self.flushes = 0
        self.scalar_calls = 0

    async def scalar(self, statement: object) -> object | None:
        self.scalar_calls += 1
        return self.existing

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        self.flushes += 1


def make_record(**overrides: object) -> ProcurementLotRecord:
    values = {
        "id": 7,
        "source_code": "zakupki",
        "external_id": "123",
        "registry_number": "0123456789",
        "law": "44-ФЗ",
        "title": "Поставка спецодежды",
        "status": "Подача заявок",
        "customer_name": "Заказчик",
        "initial_price_value": Decimal("2000000"),
        "application_deadline_at": NOW + timedelta(days=5),
        "notice_url": "https://zakupki.gov.ru/notice",
        "category": "Спецодежда",
        "matched_keywords": ["спецодежда"],
        "excluded_keywords": [],
        "attractiveness_score": 82,
        "attractiveness_level": "priority",
        "attractiveness_reasons": ["маржинальность выше 25%"],
        "workflow_status": "new",
        "net_profit": Decimal("700000"),
        "profitability": Decimal("0.25"),
        "content_hash": "hash",
        "normalized_item": {},
        "raw_item": {},
    }
    values.update(overrides)
    return ProcurementLotRecord(**values)


class ProcurementNotificationTests(unittest.IsolatedAsyncioTestCase):
    def test_eligibility_detects_priority_profitability_profit_and_deadline_events(self) -> None:
        record = make_record(application_deadline_at=NOW + timedelta(hours=40))

        events = evaluate_procurement_notification_events(record, now=NOW)
        event_types = {event.event_type for event in events}

        self.assertIn("priority_tender", event_types)
        self.assertIn("net_profit_gt_500k", event_types)
        self.assertIn("profitability_gt_20", event_types)
        self.assertIn("deadline_under_48h", event_types)
        self.assertEqual(next(event.priority for event in events if event.event_type == "deadline_under_48h"), "urgent")

    def test_owner_decision_ready_event_uses_workflow_status(self) -> None:
        events = evaluate_procurement_notification_events(make_record(workflow_status="decision"), now=NOW)

        self.assertIn("owner_decision_ready", {event.event_type for event in events})

    async def test_enqueue_creates_pending_entries_and_message_payloads(self) -> None:
        session = FakeSession()

        entries = await enqueue_procurement_telegram_notifications(session, make_record(), now=NOW)

        self.assertGreaterEqual(len(entries), 3)
        self.assertEqual(session.flushes, 1)
        self.assertTrue(all(entry.status == TelegramNotificationStatus.PENDING.value for entry in entries))
        self.assertTrue(all(entry.procurement_lot_record_id == 7 for entry in entries))
        self.assertTrue(all(entry.dedupe_key.startswith("procurement-telegram:7:") for entry in entries))
        self.assertIn("Тендер требует внимания", entries[0].message_payload["text"])
        self.assertEqual(entries[0].message_payload["parse_mode"], "HTML")

    async def test_duplicate_suppression_skips_existing_pending_or_sent_event(self) -> None:
        existing = ProcurementTelegramNotificationOutbox(
            procurement_lot_record_id=7,
            event_type="priority_tender",
            dedupe_key="existing",
            cooldown_key="existing",
            status=TelegramNotificationStatus.PENDING.value,
            priority="high",
            message_payload={},
            event_hash="hash",
            scheduled_at=NOW,
        )
        session = FakeSession(existing=existing)

        entries = await enqueue_procurement_telegram_notifications(session, make_record(), now=NOW)

        self.assertEqual(entries, [])
        self.assertEqual(session.added, [])
        self.assertEqual(session.flushes, 0)


if __name__ == "__main__":
    unittest.main()
