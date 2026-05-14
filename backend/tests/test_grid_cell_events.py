from __future__ import annotations

import unittest
from uuid import uuid4

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.models.grid import GridCellEventModel
from app.services.grid_state import record_grid_cell_events_from_payloads


class FakeSession:
    def __init__(self) -> None:
        self.added = []
        self.flushed = False

    def add(self, value) -> None:  # noqa: ANN001
        self.added.append(value)

    async def flush(self) -> None:
        self.flushed = True


class GridCellEventTests(unittest.IsolatedAsyncioTestCase):
    def test_grid_cell_event_table_compiles_for_postgres(self) -> None:
        ddl = str(CreateTable(GridCellEventModel.__table__).compile(dialect=postgresql.dialect()))

        self.assertIn("grid_cell_events", ddl)
        self.assertIn("operation_id UUID NOT NULL", ddl)
        self.assertIn("before_value JSONB", ddl)
        self.assertIn("after_value JSONB", ddl)

    async def test_record_grid_cell_events_from_operation_payloads_pairs_before_after_values(self) -> None:
        session = FakeSession()
        operation_id = uuid4()

        events = await record_grid_cell_events_from_payloads(
            session,
            operation_id=operation_id,
            workspace_id="default",
            table_id="procurement-lots",
            undo_payload={"edits": [{"rowId": "zakupki:1", "columnId": "workflowStatus", "value": "new"}]},
            redo_payload={"edits": [{"rowId": "zakupki:1", "columnId": "workflowStatus", "value": "decision"}]},
        )

        self.assertTrue(session.flushed)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].operation_id, operation_id)
        self.assertEqual(events[0].row_id, "zakupki:1")
        self.assertEqual(events[0].column_id, "workflowStatus")
        self.assertEqual(events[0].before_value, {"value": "new"})
        self.assertEqual(events[0].after_value, {"value": "decision"})


if __name__ == "__main__":
    unittest.main()
