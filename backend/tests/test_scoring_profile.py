from __future__ import annotations

import unittest
from decimal import Decimal

from app.schemas.scoring_profile import LotScoringProfile, build_lot_scoring_profile_hash


class ScoringProfileTests(unittest.TestCase):
    def test_same_profile_gives_same_hash(self) -> None:
        profile = LotScoringProfile(
            profile_identifier="profile-1",
            target_regions=["Московская область", "Москва"],
            target_categories=["Спецтехника", "Оборудование"],
            budget_min=Decimal("1000000"),
            budget_max=Decimal("2500000"),
            minimum_roi=Decimal("0.25"),
            minimum_discount=Decimal("0.15"),
            allowed_legal_risks=["low", "medium"],
            max_distance_km=Decimal("75"),
            stop_words=["квартира", "личные вещи"],
            desired_keywords=["экскаватор", "погрузчик"],
            strategy="balanced",
            weights={"economics": Decimal("1.5"), "risk": Decimal("0.8")},
        )

        self.assertEqual(build_lot_scoring_profile_hash(profile), build_lot_scoring_profile_hash(profile))

    def test_reordered_lists_normalize_deterministically(self) -> None:
        base = LotScoringProfile(
            profile_identifier="profile-1",
            target_regions=["Москва", "Московская область"],
            target_categories=["Оборудование", "Спецтехника"],
            allowed_legal_risks=["medium", "low"],
            stop_words=["личные вещи", "квартира"],
            desired_keywords=["погрузчик", "экскаватор"],
            weights={"risk": Decimal("0.8"), "economics": Decimal("1.5")},
        )
        reordered = LotScoringProfile(
            profile_identifier="profile-1",
            target_regions=["Московская область", "Москва"],
            target_categories=["Спецтехника", "Оборудование"],
            allowed_legal_risks=["low", "medium"],
            stop_words=["квартира", "личные вещи"],
            desired_keywords=["экскаватор", "погрузчик"],
            weights={"economics": Decimal("1.5"), "risk": Decimal("0.8")},
        )

        self.assertEqual(build_lot_scoring_profile_hash(base), build_lot_scoring_profile_hash(reordered))
        self.assertEqual(base.canonical_payload(), reordered.canonical_payload())

    def test_changed_profile_preference_changes_hash(self) -> None:
        base = LotScoringProfile(
            profile_identifier="profile-1",
            target_regions=["Москва"],
            budget_max=Decimal("2000000"),
            strategy="balanced",
        )
        changed = base.model_copy(update={"budget_max": Decimal("2500000"), "strategy": "aggressive"})

        self.assertNotEqual(build_lot_scoring_profile_hash(base), build_lot_scoring_profile_hash(changed))

    def test_empty_default_profile_is_stable(self) -> None:
        first = LotScoringProfile()
        second = LotScoringProfile()

        self.assertEqual(first.canonical_payload(), second.canonical_payload())
        self.assertEqual(build_lot_scoring_profile_hash(first), build_lot_scoring_profile_hash(second))


if __name__ == "__main__":
    unittest.main()
