from __future__ import annotations

import unittest
from types import SimpleNamespace

from sqlalchemy.dialects import postgresql
from unittest.mock import AsyncMock, patch

from app.schemas.analysis_config import (
    AnalysisCategoryRule,
    AnalysisLegalRiskRules,
    AuctionAnalysisConfigUpdate,
    OwnerScoringProfile,
    ScoringDimensionWeights,
)
from app.services.auction_analysis_config import auction_analysis_config_service
from app.services.auction_scoring_invalidation import invalidate_records_for_scoring_config_change


class FakeSession:
    def __init__(self, rowcount: int = 0) -> None:
        self.rowcount = rowcount
        self.executed = []
        self.storage: dict[str, object] = {}

    async def execute(self, statement):
        self.executed.append(statement)
        return SimpleNamespace(rowcount=self.rowcount)

    async def get(self, model, key):  # noqa: ANN001
        return self.storage.get(key)

    def add(self, obj):  # noqa: ANN001
        self.storage[obj.id] = obj

    async def commit(self) -> None:
        return None

    async def refresh(self, obj) -> None:  # noqa: ANN001
        self.storage[obj.id] = obj


class AuctionAnalysisConfigInvalidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_scoring_config_change_invalidation_stales_identity_without_touching_score_payload(self) -> None:
        session = FakeSession(rowcount=3)

        affected = await invalidate_records_for_scoring_config_change(
            session,
            current_scoring_version="deterministic-v2",
        )

        self.assertEqual(affected, 3)
        statement = session.executed[0]
        sql = str(statement.compile(dialect=postgresql.dialect()))
        self.assertIn("scoring_version=%(scoring_version)s", sql)
        self.assertIn("score_input_hash=%(score_input_hash)s", sql)
        self.assertNotIn("rating_score", sql)
        self.assertNotIn("rating_level", sql)
        self.assertNotIn("score_breakdown", sql)

    async def test_queue_recalculation_delegates_to_scoring_config_invalidation(self) -> None:
        session = FakeSession(rowcount=5)

        with patch(
            "app.services.auction_analysis_config.invalidate_records_for_scoring_config_change",
            AsyncMock(return_value=5),
        ) as invalidate_records:
            affected = await auction_analysis_config_service.queue_recalculation(session)

        self.assertEqual(affected, 5)
        invalidate_records.assert_awaited_once_with(session, current_scoring_version="deterministic-v2")

    async def test_procurement_defaults_are_seeded_separately(self) -> None:
        session = FakeSession()

        config = await auction_analysis_config_service.get(session, source="procurement")
        runtime = await auction_analysis_config_service.get_runtime_config(session, source="procurement")

        self.assertEqual(config.id, "procurement")
        self.assertIn("Спецодежда", runtime.category_keywords)
        self.assertIn("Униформа", runtime.category_keywords)
        self.assertIn("обувь", runtime.exclusion_keywords)
        self.assertNotIn("Земля и базы", runtime.category_keywords)

    async def test_procurement_config_update_isolated_from_auction_defaults(self) -> None:
        session = FakeSession()
        payload = AuctionAnalysisConfigUpdate(
            category_rules=[AnalysisCategoryRule(category="СИЗ", keywords=["каски", "респираторы"])],
            exclusion_keywords=["перчатки"],
            legal_risk_rules=AnalysisLegalRiskRules(),
            owner_profile=OwnerScoringProfile(),
            dimension_weights=ScoringDimensionWeights(),
        )

        updated = await auction_analysis_config_service.update(session, payload, source="procurement")
        runtime = await auction_analysis_config_service.get_runtime_config(session, source="procurement")

        self.assertEqual(updated.id, "procurement")
        self.assertEqual(runtime.category_keywords, {"СИЗ": ("каски", "респираторы")})
        self.assertEqual(runtime.exclusion_keywords, ("перчатки",))
        self.assertEqual(session.storage["procurement"].id, "procurement")


if __name__ == "__main__":
    unittest.main()
