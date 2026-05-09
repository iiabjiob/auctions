from __future__ import annotations

import unittest
from unittest.mock import AsyncMock

from app.infrastructure.db.database import apply_read_statement_timeout


class DatabaseStatementTimeoutTests(unittest.IsolatedAsyncioTestCase):
    async def test_read_statement_timeout_sets_postgres_cancel_guard(self) -> None:
        session = AsyncMock()

        await apply_read_statement_timeout(session, timeout_ms=3500)

        session.execute.assert_awaited_once()
        statement = session.execute.await_args.args[0]
        self.assertEqual(str(statement), "SET LOCAL statement_timeout = 3500")

    async def test_zero_read_statement_timeout_is_disabled(self) -> None:
        session = AsyncMock()

        await apply_read_statement_timeout(session, timeout_ms=0)

        session.execute.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
