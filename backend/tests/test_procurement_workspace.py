from __future__ import annotations

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.models.procurement import ProcurementLotDetailCache, ProcurementLotObservation, ProcurementLotRecord
from app.services.procurement_workspace import build_procurement_workspace_response, get_procurement_lot_workspace


NOW = datetime(2026, 5, 14, 12, tzinfo=UTC)


def make_record() -> ProcurementLotRecord:
    return ProcurementLotRecord(
        id=1,
        source_code="zakupki",
        external_id="123",
        registry_number="123",
        title="Поставка спецодежды",
        status="Подача заявок",
        customer_name="Заказчик",
        customer_inn="7700000000",
        initial_price_value=1000000,
        application_deadline_at=NOW,
        notice_url="https://zakupki.gov.ru/epz/order/notice/common-info.html?regNumber=123",
        content_hash="hash",
        first_seen_at=NOW,
        last_seen_at=NOW,
        is_new=True,
        lifecycle_status="active",
        workflow_status="new",
        attractiveness_score=80,
        attractiveness_level="priority",
        attractiveness_reasons=[],
        matched_keywords=[],
        excluded_keywords=[],
        calculator_inputs={},
        calculator_scenarios={},
        normalized_item={},
        raw_item={},
    )


class ProcurementWorkspaceTests(unittest.IsolatedAsyncioTestCase):
    async def test_build_workspace_response_includes_detail_cache_documents_and_changes(self) -> None:
        record = make_record()
        detail_cache = ProcurementLotDetailCache(
            procurement_lot_record_id=1,
            fetched_at=NOW,
            content_hash="detail-hash",
            detail_payload={"fields": {"Требования": "ТР ТС 019/2011", "Оплата": "30 дней"}},
            documents=[{"title": "ТЗ", "url": "https://zakupki.gov.ru/doc.pdf", "source_url": "https://zakupki.gov.ru/docs"}],
        )
        last_observation = ProcurementLotObservation(
            procurement_lot_record_id=1,
            observed_at=NOW,
            content_hash="hash",
            status="Подача заявок",
            normalized_item={"title": "Поставка спецодежды"},
            raw_item={},
        )
        session = SimpleNamespace(scalar=AsyncMock(side_effect=[1, 1, last_observation, None, NOW]))

        response = await build_procurement_workspace_response(session, record, detail_cache)

        self.assertEqual(response.record.registry_number, "123")
        self.assertEqual(response.detail_cached_at, NOW)
        self.assertEqual(response.documents[0].title, "ТЗ")
        self.assertEqual(response.raw_fields[0].name, "Требования")
        self.assertEqual(response.changes.observations_count, 1)
        self.assertEqual(response.current_enrichment_state.attempt_count, 0)

    async def test_get_workspace_refresh_calls_enrichment_and_commits(self) -> None:
        record = make_record()
        detail_cache = ProcurementLotDetailCache(
            procurement_lot_record_id=1,
            fetched_at=NOW,
            content_hash="detail-hash",
            detail_payload={},
            documents=[],
        )
        session = SimpleNamespace(commit=AsyncMock())

        with (
            patch("app.services.procurement_workspace.find_procurement_lot_record", AsyncMock(return_value=record)),
            patch("app.services.procurement_workspace.enrich_procurement_lot_record", AsyncMock(return_value=True)) as enrich,
            patch("app.services.procurement_workspace.get_procurement_lot_detail_cache", AsyncMock(return_value=detail_cache)),
            patch("app.services.procurement_workspace.build_procurement_workspace_response", AsyncMock(return_value={"workspace": True})) as build_response,
        ):
            response = await get_procurement_lot_workspace(session, source="zakupki", external_id="123", refresh=True)

        enrich.assert_awaited_once_with(session, record)
        session.commit.assert_awaited_once()
        build_response.assert_awaited_once_with(session, record, detail_cache)
        self.assertEqual(response, {"workspace": True})

    async def test_get_workspace_raises_for_missing_record(self) -> None:
        session = SimpleNamespace()

        with patch("app.services.procurement_workspace.find_procurement_lot_record", AsyncMock(return_value=None)):
            with self.assertRaises(LookupError):
                await get_procurement_lot_workspace(session, source="zakupki", external_id="missing")


if __name__ == "__main__":
    unittest.main()
