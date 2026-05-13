from __future__ import annotations

import unittest

from pydantic import ValidationError

from app.schemas.user_interest_profiles import (
    UserInterestProfileCreate,
    UserInterestProfileFromPreset,
    UserInterestProfileUpdate,
)


class UserInterestProfileSchemaTests(unittest.TestCase):
    def test_create_normalizes_scoring_profile_payload(self) -> None:
        profile = UserInterestProfileCreate(
            name="Special machinery",
            profile_payload={
                "target_categories": ["Спецтехника", " спецтехника "],
                "budget_min": "2000000",
                "desired_keywords": ["экскаватор"],
            },
            min_rating=80,
        )

        self.assertEqual(profile.profile_payload["target_categories"], ["Спецтехника"])
        self.assertEqual(profile.profile_payload["budget_min"], "2000000")
        self.assertEqual(profile.profile_payload["desired_keywords"], ["экскаватор"])
        self.assertEqual(profile.notification_priority_threshold, "medium")
        self.assertTrue(profile.telegram_enabled)
        self.assertTrue(profile.is_active)
        self.assertIsNone(profile.source_filter_preset_id)

    def test_update_allows_partial_payload(self) -> None:
        profile = UserInterestProfileUpdate(min_rating=70, telegram_enabled=False)

        self.assertEqual(profile.min_rating, 70)
        self.assertFalse(profile.telegram_enabled)
        self.assertIsNone(profile.profile_payload)

    def test_rejects_invalid_profile_payload(self) -> None:
        with self.assertRaises(ValidationError):
            UserInterestProfileCreate(
                name="Invalid",
                profile_payload={"strategy": "invalid"},
            )

    def test_rejects_invalid_min_rating_and_priority_threshold(self) -> None:
        with self.assertRaises(ValidationError):
            UserInterestProfileCreate(name="Invalid", min_rating=101)

        with self.assertRaises(ValidationError):
            UserInterestProfileCreate(name="Invalid", notification_priority_threshold="minor")

    def test_from_preset_payload_validates_controls(self) -> None:
        payload = UserInterestProfileFromPreset(
            preset_id="preset_1",
            name="BMW Telegram",
            min_rating=85,
            telegram_enabled=True,
        )

        self.assertEqual(payload.preset_id, "preset_1")
        self.assertEqual(payload.name, "BMW Telegram")
        self.assertEqual(payload.min_rating, 85)


if __name__ == "__main__":
    unittest.main()
