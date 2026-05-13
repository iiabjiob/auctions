from __future__ import annotations

import unittest

from app.models import UserInterestProfileModel
from app.schemas.scoring_profile import LotScoringProfile, build_lot_scoring_profile_hash
from app.services.user_interest_matching import (
    build_lot_scoring_profile_from_interest,
    evaluate_user_interest_match,
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


class UserInterestMatchingTests(unittest.TestCase):
    def test_build_lot_scoring_profile_from_interest_validates_payload(self) -> None:
        interest = make_interest_profile(
            profile_payload={
                "profile_identifier": "bmw",
                "desired_keywords": ["BMW"],
                "budget_min": "1000000",
            }
        )

        profile = build_lot_scoring_profile_from_interest(interest)

        self.assertEqual(profile.profile_identifier, "bmw")
        self.assertEqual(profile.desired_keywords, ["BMW"])
        self.assertEqual(profile.budget_min, 1000000)

    def test_bmw_keyword_profile_matches_bmw_lot(self) -> None:
        record = make_record()
        record.rating_score = 90
        record.lot_name = "BMW M5"
        record.datagrid_row["lot_name"] = "BMW M5"
        record.normalized_item["lot"]["category"] = "Автомобили"
        record.normalized_item["lot"]["model_category"] = "BMW"
        interest = make_interest_profile(
            profile_payload={
                "profile_identifier": "bmw-cars",
                "target_categories": ["Автомобили"],
                "desired_keywords": ["BMW"],
            },
            min_rating=80,
        )

        result = evaluate_user_interest_match(record, interest)

        self.assertTrue(result.matches)
        self.assertEqual(result.blockers, ())
        self.assertIn("Категория соответствует профилю", result.reasons)
        self.assertIn("Есть желательное слово: bmw", result.reasons)
        self.assertEqual(
            result.profile_hash,
            build_lot_scoring_profile_hash(LotScoringProfile.model_validate(interest.profile_payload)),
        )

    def test_special_machinery_budget_min_blocks_cheap_lot(self) -> None:
        record = make_record()
        record.rating_score = 95
        interest = make_interest_profile(
            profile_payload={
                "target_categories": ["Спецтехника"],
                "budget_min": "2000000",
            },
            min_rating=80,
        )

        result = evaluate_user_interest_match(record, interest, detail_cache=make_detail_cache())

        self.assertFalse(result.matches)
        self.assertIn("Цена ниже целевого бюджета", result.blockers)
        self.assertIn("Категория соответствует профилю", result.reasons)

    def test_stop_words_block_notification(self) -> None:
        record = make_record()
        record.rating_score = 90
        record.lot_name = "Экскаватор битый"
        record.datagrid_row["lot_name"] = "Экскаватор битый"
        interest = make_interest_profile(profile_payload={"stop_words": ["битый"]})

        result = evaluate_user_interest_match(record, interest, detail_cache=make_detail_cache())

        self.assertFalse(result.matches)
        self.assertIn("Профиль исключает слово: битый", result.blockers)

    def test_min_rating_blocks_low_rating(self) -> None:
        record = make_record()
        record.rating_score = 60
        interest = make_interest_profile(profile_payload={"target_categories": ["Спецтехника"]}, min_rating=80)

        result = evaluate_user_interest_match(record, interest, detail_cache=make_detail_cache())

        self.assertFalse(result.matches)
        self.assertIn("Рейтинг ниже порога профиля: 60 < 80", result.blockers)
        self.assertIn("Категория соответствует профилю", result.reasons)

    def test_inactive_or_telegram_disabled_profile_blocks_notification_path(self) -> None:
        record = make_record()
        record.rating_score = 90
        inactive = make_interest_profile(is_active=False)
        telegram_disabled = make_interest_profile(telegram_enabled=False)

        inactive_result = evaluate_user_interest_match(record, inactive, detail_cache=make_detail_cache())
        telegram_result = evaluate_user_interest_match(record, telegram_disabled, detail_cache=make_detail_cache())
        non_notification_result = evaluate_user_interest_match(
            record,
            telegram_disabled,
            detail_cache=make_detail_cache(),
            require_telegram_enabled=False,
        )

        self.assertFalse(inactive_result.matches)
        self.assertIn("Профиль интересов отключен", inactive_result.blockers)
        self.assertFalse(telegram_result.matches)
        self.assertIn("Telegram-уведомления отключены для профиля", telegram_result.blockers)
        self.assertTrue(non_notification_result.matches)


if __name__ == "__main__":
    unittest.main()
