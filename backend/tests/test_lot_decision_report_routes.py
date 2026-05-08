from __future__ import annotations

import unittest
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from app.api.v1.auctions.router import get_lot_decision_report, list_lot_decision_reports
from app.schemas.lot_decision_report import (
    ActionRecommendation,
    DecisionLevel,
    LotDecisionReason,
    LotDecisionReport,
    LotEconomicsDecision,
)


GENERATED_AT = datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc)


class FakeScalars:
    def __init__(self, values: list[object]) -> None:
        self.values = values

    def all(self) -> list[object]:
        return self.values


class FakeSession:
    def __init__(self, *, scalar_result: object | None = None, scalars_result: list[object] | None = None) -> None:
        self.scalar_result = scalar_result
        self.scalars_result = scalars_result or []
        self.scalar_statements = []
        self.scalars_statements = []

    async def scalar(self, statement):  # noqa: ANN001
        self.scalar_statements.append(statement)
        return self.scalar_result

    async def scalars(self, statement):  # noqa: ANN001
        self.scalars_statements.append(statement)
        return FakeScalars(self.scalars_result)


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
        "deadline": "10.05.2026 18:00",
        "rating_score": 92,
        "rating_level": "high",
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
        "reasons": (LotDecisionReason(code="score.reason.1", message="High score", source="score_breakdown"),),
        "risks": (),
        "next_actions": (),
        "generated_at": GENERATED_AT,
    }
    values.update(overrides)
    return LotDecisionReport(**values)


def make_snapshot(report: LotDecisionReport, **overrides: object) -> SimpleNamespace:
    values = {
        "id": 1,
        "lot_record_id": report.record_id,
        "profile_hash": report.profile_hash,
        "report_payload": report.model_dump(mode="json"),
        "generated_at": report.generated_at,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class LotDecisionReportRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_decision_report_reads_local_snapshot_without_external_fetch(self) -> None:
        report = make_report()
        session = FakeSession(scalar_result=make_snapshot(report))

        with patch("app.api.v1.auctions.router.get_source_provider") as get_source_provider:
            response = await get_lot_decision_report(
                id=1,
                profile_hash=None,
                session=session,
                current_user=SimpleNamespace(id=1),
            )

        self.assertEqual(response, report)
        self.assertEqual(len(session.scalar_statements), 1)
        get_source_provider.assert_not_called()

    async def test_get_decision_report_404_without_external_fetch(self) -> None:
        session = FakeSession(scalar_result=None)

        with patch("app.api.v1.auctions.router.get_source_provider") as get_source_provider:
            with self.assertRaises(HTTPException) as error:
                await get_lot_decision_report(
                    id=404,
                    profile_hash=None,
                    session=session,
                    current_user=SimpleNamespace(id=1),
                )

        self.assertEqual(error.exception.status_code, 404)
        self.assertEqual(error.exception.detail, "Снимок отчета по лоту не найден")
        get_source_provider.assert_not_called()

    async def test_list_bid_candidate_reports_reads_local_snapshots_without_external_fetch(self) -> None:
        report = make_report()
        session = FakeSession(scalars_result=[make_snapshot(report)])

        with patch("app.api.v1.auctions.router.get_source_provider") as get_source_provider:
            response = await list_lot_decision_reports(
                kind="bid_candidates",
                decision_level=None,
                profile_hash=None,
                notification_should_send=None,
                limit=10,
                session=session,
                current_user=SimpleNamespace(id=1),
            )

        self.assertEqual(response, [report])
        self.assertEqual(len(session.scalars_statements), 1)
        get_source_provider.assert_not_called()


if __name__ == "__main__":
    unittest.main()
