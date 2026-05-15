from __future__ import annotations

import unittest
from sqlalchemy.dialects import postgresql

from app.models import UserInterestProfileModel
from app.models.filter_preset import FilterPresetModel
from app.services.user_interest_matching import (
    build_saved_slice_match_statement,
    build_saved_slice_hash,
    evaluate_user_interest_match,
    evaluate_saved_slice_match,
)
from tests.test_lot_evidence import make_detail_cache, make_record


def make_interest_profile(**overrides: object) -> UserInterestProfileModel:
    values = {
        "id": "uip_1",
        "owner_user_id": "user-1",
        "name": "Profile",
        "profile_payload": {},
        "min_rating": 0,
        "notification_priority_threshold": "medium",
        "telegram_enabled": True,
        "is_active": True,
    }
    values.update(overrides)
    return UserInterestProfileModel(**values)


def make_preset(**overrides: object) -> FilterPresetModel:
    values = {
        "id": "preset_1",
        "owner_user_id": "user-1",
        "scope": "auction",
        "name": "BMW slice",
        "filters": {
            "period": "month",
            "source": "tbankrot",
            "status": "Accepting applications",
            "minRating": 80,
        },
        "grid_view": {
            "state": {
                "rows": {
                    "snapshot": {
                        "filterModel": {
                            "quickFilter": {"query": "BMW"},
                        },
                    },
                },
            },
        },
        "is_favorite": False,
    }
    values.update(overrides)
    return FilterPresetModel(**values)


class FakeSession:
    def __init__(self, scalar_result: object | None = None) -> None:
        self.scalar_result = scalar_result
        self.scalar_statements: list[object] = []

    async def scalar(self, statement):  # noqa: ANN001
        self.scalar_statements.append(statement)
        return self.scalar_result


class UserInterestMatchingTests(unittest.IsolatedAsyncioTestCase):
    async def test_profile_without_saved_slice_link_does_not_match(self) -> None:
        record = make_record()
        record.rating_score = 90
        interest = make_interest_profile(source_filter_preset_id=None)

        result = await evaluate_user_interest_match(record, interest)

        self.assertFalse(result.matches)
        self.assertEqual(result.reasons, ())
        self.assertIn("Профиль не привязан к сохраненному срезу", result.blockers)

    async def test_inactive_or_telegram_disabled_profile_blocks_notification_path(self) -> None:
        record = make_record()
        record.rating_score = 90
        preset = make_preset()
        inactive = make_interest_profile(is_active=False, source_filter_preset_id="preset_1")
        telegram_disabled = make_interest_profile(source_filter_preset_id="preset_1", telegram_enabled=False)
        telegram_allowed = make_interest_profile(source_filter_preset_id="preset_1", telegram_enabled=False)
        session = FakeSession(1)

        inactive_result = await evaluate_saved_slice_match(session, record, inactive, preset)
        telegram_result = await evaluate_saved_slice_match(session, record, telegram_disabled, preset)
        non_notification_result = await evaluate_saved_slice_match(
            session,
            record,
            telegram_allowed,
            preset,
            require_telegram_enabled=False,
        )

        self.assertFalse(inactive_result.matches)
        self.assertIn("Профиль интересов отключен", inactive_result.blockers)
        self.assertFalse(telegram_result.matches)
        self.assertIn("Telegram-уведомления отключены для профиля", telegram_result.blockers)
        self.assertTrue(non_notification_result.matches)

    async def test_saved_slice_match_uses_saved_slice_hash_and_membership(self) -> None:
        record = make_record()
        record.rating_score = 90
        interest = make_interest_profile(source_filter_preset_id="preset_1", min_rating=80)
        preset = make_preset()
        session = FakeSession(1)

        result = await evaluate_saved_slice_match(session, record, interest, preset)

        self.assertTrue(result.matches)
        self.assertEqual(result.profile_hash, build_saved_slice_hash(preset))
        self.assertIn("Лот попадает в сохраненный срез: BMW slice", result.reasons)
        self.assertEqual(len(session.scalar_statements), 1)

    def test_saved_slice_statement_uses_quick_filter_and_grid_filters(self) -> None:
        preset = make_preset()

        statement = build_saved_slice_match_statement(1, preset)
        sql = str(statement.compile(dialect=postgresql.dialect()))

        self.assertIn("auction_lot_records", sql)
        self.assertIn("rating_score", sql)
        self.assertIn("status", sql)
        self.assertIn("LIKE", sql)


if __name__ == "__main__":
    unittest.main()
