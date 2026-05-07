from __future__ import annotations

import unittest
from decimal import Decimal

from app.schemas.lot_evidence import (
    LotCategoryFacts,
    LotConstraintFacts,
    LotDeadlineFacts,
    LotEvidence,
    LotFreshnessFacts,
    LotLegalFacts,
    LotLocationFacts,
    LotPriceFacts,
)
from app.schemas.scoring_profile import LotScoringProfile
from app.services.scoring_profile_fit import evaluate_lot_profile_fit, resolve_profile_fit_weights


def make_evidence(**overrides: object) -> LotEvidence:
    values = {
        "source_code": "tbankrot",
        "auction_external_id": "auction-1",
        "lot_external_id": "lot-1",
        "lot_number": "1",
        "content_hash": "content-hash",
        "price": LotPriceFacts(current_price=Decimal("1000000"), initial_price=Decimal("1000000")),
        "location": LotLocationFacts(region="Московская область", city="Химки", address="ул. Ленина, 1"),
        "category": LotCategoryFacts(category="Спецтехника", model_category="Спецтехника", lot_name="Экскаватор"),
        "legal": LotLegalFacts(has_documents=True, has_photos=True),
        "deadlines": LotDeadlineFacts(application_deadline="05.05.2026 18:00"),
        "constraints": LotConstraintFacts(description_present=True, inspection_order="По записи"),
        "freshness": LotFreshnessFacts(is_new=True),
    }
    values.update(overrides)
    return LotEvidence(**values)


class ScoringProfileFitTests(unittest.TestCase):
    def test_profile_fit_weight_defaults_and_clamping(self) -> None:
        self.assertEqual(resolve_profile_fit_weights(None), {"match_bonus": 4, "blocker_penalty": -5, "neutral": 0})

        profile = LotScoringProfile(
            weights={
                "profile_fit.match_bonus": Decimal("100"),
                "profile_fit.blocker_penalty": Decimal("-100"),
                "profile_fit.neutral": Decimal("3"),
            }
        )
        self.assertEqual(
            resolve_profile_fit_weights(profile),
            {"match_bonus": 10, "blocker_penalty": -10, "neutral": 3},
        )

    def test_matching_region_category_budget_produces_positive_fit(self) -> None:
        evidence = make_evidence()
        profile = LotScoringProfile(
            profile_identifier="profile-1",
            target_regions=["Московская область"],
            target_categories=["Спецтехника"],
            budget_min=Decimal("900000"),
            budget_max=Decimal("1200000"),
        )

        fit = evaluate_lot_profile_fit(evidence, profile)

        self.assertTrue(fit.matches_profile)
        self.assertTrue(fit.dimensions["region"].matched)
        self.assertTrue(fit.dimensions["category"].matched)
        self.assertTrue(fit.dimensions["budget"].matched)
        self.assertIn("Регион соответствует профилю", fit.reasons)
        self.assertIn("Категория соответствует профилю", fit.reasons)
        self.assertIn("Цена укладывается в бюджет", fit.reasons)
        self.assertEqual(fit.blockers, [])

    def test_stop_words_create_blockers(self) -> None:
        evidence = make_evidence(category=LotCategoryFacts(category="Спецтехника", model_category="Спецтехника", lot_name="Экскаватор в залоге"))
        profile = LotScoringProfile(stop_words=["залог"])

        fit = evaluate_lot_profile_fit(evidence, profile)

        self.assertFalse(fit.matches_profile)
        self.assertIn("Профиль исключает слово: залог", fit.blockers)
        self.assertFalse(fit.dimensions["keywords"].matched)
        self.assertIn("Профиль исключает слово: залог", fit.dimensions["keywords"].blockers)

    def test_risk_outside_allowed_risks_creates_blocker(self) -> None:
        evidence = make_evidence(legal=LotLegalFacts(has_documents=True, has_photos=True, legal_risk_signals=("high",)))
        profile = LotScoringProfile(allowed_legal_risks=["low"])

        fit = evaluate_lot_profile_fit(evidence, profile)

        self.assertFalse(fit.matches_profile)
        self.assertIn("Юридический риск вне профиля", fit.blockers)
        self.assertFalse(fit.dimensions["risk"].matched)
        self.assertIn("Юридический риск вне профиля", fit.dimensions["risk"].blockers)

    def test_missing_optional_fields_do_not_crash(self) -> None:
        evidence = LotEvidence(
            source_code="tbankrot",
            auction_external_id="auction-1",
            lot_external_id="lot-1",
        )
        profile = LotScoringProfile(max_distance_km=Decimal("25"))

        fit = evaluate_lot_profile_fit(evidence, profile)

        self.assertTrue(fit.matches_profile)
        self.assertFalse(fit.dimensions["distance"].available)
        self.assertEqual(fit.blockers, [])
        self.assertIn("Дистанция не оценена без локальной геометрии", fit.reasons)


if __name__ == "__main__":
    unittest.main()
