from __future__ import annotations

import unittest
from datetime import UTC, datetime

from sqlalchemy.dialects import postgresql

from app.models.auction import AuctionSourceHttpExchange
from app.services.source_http_diagnostics import (
    begin_source_http_diagnostics,
    collect_source_http_diagnostics,
    get_source_diagnostics,
    persist_source_http_diagnostics,
    record_source_http_exchange,
)


class SourceHttpDiagnosticsTests(unittest.IsolatedAsyncioTestCase):
    def test_records_exchange_in_active_context(self) -> None:
        token = begin_source_http_diagnostics()
        record_source_http_exchange(
            source_code="tbankrot",
            operation="list",
            method="GET",
            url="https://tbankrot.ru/?page=1",
            started_at=datetime(2026, 5, 13, 10, 0, tzinfo=UTC),
            completed_at=datetime(2026, 5, 13, 10, 0, 1, tzinfo=UTC),
            status_code=200,
            request_bytes=0,
            response_bytes=2048,
        )

        events = collect_source_http_diagnostics(token)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].source_code, "tbankrot")
        self.assertEqual(events[0].operation, "list")
        self.assertEqual(events[0].duration_ms, 1000)
        self.assertEqual(events[0].response_bytes, 2048)
        self.assertTrue(events[0].ok)

    async def test_persist_adds_exchange_models(self) -> None:
        class FakeSession:
            def __init__(self) -> None:
                self.added = []

            def add_all(self, values) -> None:  # noqa: ANN001
                self.added.extend(values)

        token = begin_source_http_diagnostics()
        record_source_http_exchange(
            source_code="tbankrot",
            operation="lot_detail",
            method="GET",
            url="https://tbankrot.ru/item?id=123",
            started_at=datetime(2026, 5, 13, 10, 0, tzinfo=UTC),
            completed_at=datetime(2026, 5, 13, 10, 0, 2, tzinfo=UTC),
            status_code=500,
            request_bytes=0,
            response_bytes=512,
            error=RuntimeError("failed"),
        )
        events = collect_source_http_diagnostics(token)
        session = FakeSession()

        await persist_source_http_diagnostics(session, events)

        self.assertEqual(len(session.added), 1)
        self.assertIsInstance(session.added[0], AuctionSourceHttpExchange)
        self.assertFalse(session.added[0].ok)
        self.assertEqual(session.added[0].error_type, "RuntimeError")

    async def test_diagnostics_queries_compile_for_postgres(self) -> None:
        class CompileOnlySession:
            async def execute(self, statement):  # noqa: ANN001
                statement.compile(dialect=postgresql.dialect())
                return _EmptyResult()

        response = await get_source_diagnostics(
            CompileOnlySession(),
            range_name="day",
            current_time=datetime(2026, 5, 13, 10, 0, tzinfo=UTC),
        )

        self.assertEqual(response.range, "day")


class _EmptyResult:
    def one(self):
        return _Row(
            request_count=0,
            success_count=0,
            error_count=0,
            inbound_bytes=0,
            outbound_bytes=0,
            average_duration_ms=None,
        )

    def all(self):
        return []


class _Row:
    def __init__(self, **kwargs) -> None:
        self.__dict__.update(kwargs)
