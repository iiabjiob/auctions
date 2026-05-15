from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.models import UserInterestProfileModel, UserTelegramBindingModel
from app.models.filter_preset import FilterPresetModel
from app.models.procurement import ProcurementLotRecord
from app.schemas.lot_decision_report import TelegramNotificationStatus
from app.services.procurement_notifications import enqueue_procurement_telegram_notifications, build_saved_slice_hash


NOW = datetime(2026, 5, 13, 12, tzinfo=UTC)


class FakeSession:
    def __init__(
        self,
        scalar_results: list[object | None] | None = None,
        scalars_results: list[list[object]] | None = None,
    ) -> None:
        self.scalar_results = list(scalar_results or [])
        self.scalars_results = list(scalars_results or [])
        self.added: list[object] = []
        self.flushes = 0
        self.scalar_calls = 0
        self.scalars_calls = 0
        self.statements: list[object] = []

    async def scalar(self, statement: object) -> object | None:
        self.scalar_calls += 1
        self.statements.append(statement)
        if self.scalar_results:
            return self.scalar_results.pop(0)
        return None

    async def scalars(self, statement: object):
        self.scalars_calls += 1
        self.statements.append(statement)
        return FakeScalars(self.scalars_results.pop(0) if self.scalars_results else [])

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        self.flushes += 1


class FakeScalars:
    def __init__(self, values: list[object]) -> None:
        self.values = values

    def all(self) -> list[object]:
        return self.values


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


def make_preset(**overrides: object) -> FilterPresetModel:
    values = {
        "id": "preset_proc_1",
        "owner_user_id": "user-1",
        "scope": "procurement",
        "name": "Спецодежда срез",
        "filters": {
            "source": "zakupki",
            "status": "Подача заявок",
            "category": "Спецодежда",
            "minScore": 75,
        },
        "grid_view": {
            "state": {
                "rows": {
                    "snapshot": {
                        "filterModel": {
                            "quickFilter": {"query": "спецодежды"},
                        },
                    },
                },
            },
        },
        "is_favorite": False,
    }
    values.update(overrides)
    return FilterPresetModel(**values)


def make_interest_profile(**overrides: object) -> UserInterestProfileModel:
    values = {
        "id": "uip_1",
        "owner_user_id": "user-1",
        "source_filter_preset_id": "preset_proc_1",
        "name": "Procurement slice",
        "profile_payload": {},
        "min_rating": 0,
        "notification_priority_threshold": "medium",
        "telegram_enabled": True,
        "is_active": True,
    }
    values.update(overrides)
    return UserInterestProfileModel(**values)


def make_binding(**overrides: object) -> UserTelegramBindingModel:
    values = {
        "user_id": "user-1",
        "telegram_chat_id": "123456789",
        "username": "procurement_user",
    }
    values.update(overrides)
    return UserTelegramBindingModel(**values)


class ProcurementNotificationTests(unittest.IsolatedAsyncioTestCase):
    async def test_enqueue_creates_pending_entry_for_matching_saved_slice(self) -> None:
        record = make_record()
        preset = make_preset()
        profile = make_interest_profile()
        session = FakeSession(
            scalar_results=[preset, 1, None, None],
            scalars_results=[[profile], [make_binding()]],
        )

        entries = await enqueue_procurement_telegram_notifications(session, record, now=NOW)

        self.assertEqual(len(entries), 1)
        self.assertEqual(session.flushes, 1)
        self.assertTrue(all(entry.status == TelegramNotificationStatus.PENDING.value for entry in entries))
        self.assertTrue(all(entry.procurement_lot_record_id == 7 for entry in entries))
        self.assertTrue(all(entry.dedupe_key.startswith("procurement-telegram:user-1:uip_1:7:") for entry in entries))
        self.assertIn("Тендер попал в сохраненный срез", entries[0].message_payload["text"])
        self.assertIn("Спецодежда срез", entries[0].message_payload["text"])
        self.assertEqual(entries[0].message_payload["parse_mode"], "HTML")

    async def test_enqueue_skips_when_no_saved_slice_matches(self) -> None:
        record = make_record(status="Черновик")
        preset = make_preset()
        profile = make_interest_profile()
        session = FakeSession(
            scalar_results=[preset, None],
            scalars_results=[[profile], [make_binding()]],
        )

        entries = await enqueue_procurement_telegram_notifications(session, record, now=NOW)

        self.assertEqual(entries, [])
        self.assertEqual(session.added, [])
        self.assertEqual(session.flushes, 0)

    async def test_enqueue_skips_duplicate_delivery_for_same_user_across_profiles(self) -> None:
        record = make_record()
        preset = make_preset()
        first = make_interest_profile(id="uip_1")
        second = make_interest_profile(id="uip_2")
        session = FakeSession(
            scalar_results=[preset, 1, None, None, preset, 1],
            scalars_results=[[first, second], [make_binding()]],
        )

        entries = await enqueue_procurement_telegram_notifications(session, record, now=NOW)

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].user_id, "user-1")
        self.assertEqual(entries[0].cooldown_key, "procurement-telegram:user-1:7")
        self.assertEqual(entries[0].event_type, "saved_slice:user-1")
        self.assertEqual(entries[0].dedupe_key, f"procurement-telegram:user-1:uip_1:7:{build_saved_slice_hash(preset)}")
        self.assertEqual(session.flushes, 1)


if __name__ == "__main__":
    unittest.main()
