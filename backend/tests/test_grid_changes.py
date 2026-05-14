from __future__ import annotations

import unittest

from app.models.grid import GridChangeEventModel
from app.services.auction_grid_state import AUCTION_LOTS_TABLE_ID
from app.services.grid_changes import get_grid_changes
from app.services.procurement_grid_state import PROCUREMENT_LOTS_TABLE_ID


class FakeScalars:
    def __init__(self, rows: list[GridChangeEventModel]) -> None:
        self._rows = rows

    def all(self) -> list[GridChangeEventModel]:
        return self._rows


class FakeSession:
    def __init__(self, *, latest_version: int | None, rows: list[GridChangeEventModel]) -> None:
        self.latest_version = latest_version
        self.rows = rows

    async def scalar(self, statement: object) -> int | None:
        return self.latest_version

    async def scalars(self, statement: object) -> FakeScalars:
        return FakeScalars(self.rows)


def make_event(
    version: int,
    event_type: str = "row_updated",
    row_id: str | None = "row-1",
    table_id: str = AUCTION_LOTS_TABLE_ID,
) -> GridChangeEventModel:
    return GridChangeEventModel(
        workspace_id="default",
        table_id=table_id,
        dataset_version=version,
        event_type=event_type,
        row_id=row_id,
        payload={"version": version},
    )


class GridChangesTests(unittest.IsolatedAsyncioTestCase):
    async def test_change_feed_maps_events_and_has_more(self) -> None:
        response = await get_grid_changes(
            FakeSession(latest_version=7, rows=[make_event(2), make_event(3), make_event(4)]),
            table_id=AUCTION_LOTS_TABLE_ID,
            since_version=1,
            limit=2,
        )

        self.assertEqual(response.dataset_version, 7)
        self.assertTrue(response.has_more)
        self.assertEqual([change.payload["version"] for change in response.changes], [2, 3])
        self.assertEqual(response.changes[0].type, "row_updated")
        self.assertEqual(response.changes[0].row_id, "row-1")

    async def test_change_feed_returns_empty_changes_with_latest_version(self) -> None:
        response = await get_grid_changes(
            FakeSession(latest_version=5, rows=[]),
            table_id=AUCTION_LOTS_TABLE_ID,
            since_version=5,
        )

        self.assertEqual(response.dataset_version, 5)
        self.assertEqual(response.changes, [])
        self.assertFalse(response.has_more)

    async def test_unknown_event_type_maps_to_invalidation(self) -> None:
        response = await get_grid_changes(
            FakeSession(latest_version=9, rows=[make_event(9, event_type="unknown", row_id=None)]),
            table_id=AUCTION_LOTS_TABLE_ID,
            since_version=8,
        )

        self.assertEqual(response.changes[0].type, "invalidation")
        self.assertIsNone(response.changes[0].row_id)

    async def test_response_uses_transport_aliases(self) -> None:
        response = await get_grid_changes(
            FakeSession(latest_version=1, rows=[make_event(1)]),
            table_id=AUCTION_LOTS_TABLE_ID,
            since_version=0,
        )

        self.assertEqual(
            response.model_dump(by_alias=True),
            {
                "datasetVersion": 1,
                "changes": [
                    {
                        "type": "row_updated",
                        "rowId": "row-1",
                        "payload": {"version": 1},
                    }
                ],
                "hasMore": False,
            },
        )

    async def test_procurement_change_feed_uses_requested_table_scope(self) -> None:
        response = await get_grid_changes(
            FakeSession(
                latest_version=12,
                rows=[
                    make_event(
                        11,
                        row_id="zakupki:123",
                        table_id=PROCUREMENT_LOTS_TABLE_ID,
                    )
                ],
            ),
            table_id=PROCUREMENT_LOTS_TABLE_ID,
            since_version=10,
        )

        self.assertEqual(response.dataset_version, 12)
        self.assertFalse(response.has_more)
        self.assertEqual(len(response.changes), 1)
        self.assertEqual(response.changes[0].row_id, "zakupki:123")
        self.assertEqual(response.changes[0].payload, {"version": 11})


if __name__ == "__main__":
    unittest.main()
