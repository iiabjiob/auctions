from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, patch

from fastapi import HTTPException

from app.api.grid_changes_router import get_changes
from app.schemas.grid_changes import GridChangeFeedResponse
from app.services.auction_grid_state import AUCTION_LOTS_TABLE_ID, DEFAULT_GRID_WORKSPACE_ID


class GridChangesRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_changes_accepts_table_id_from_header_for_package_datasource(self) -> None:
        with patch(
            "app.api.grid_changes_router.get_grid_changes",
            AsyncMock(return_value=GridChangeFeedResponse(datasetVersion=7, changes=[], hasMore=False)),
        ) as service:
            response = await get_changes(
                table_id=None,
                grid_table_id=AUCTION_LOTS_TABLE_ID,
                since_version=5,
                limit=None,
                workspace_id=None,
                session=AsyncMock(),
                current_user=SimpleNamespace(id="user-1"),
            )

        self.assertEqual(response.dataset_version, 7)
        service.assert_awaited_once_with(
            ANY,
            table_id=AUCTION_LOTS_TABLE_ID,
            since_version=5,
            workspace_id=DEFAULT_GRID_WORKSPACE_ID,
            limit=None,
        )

    async def test_changes_rejects_missing_table_scope(self) -> None:
        with self.assertRaises(HTTPException) as context:
            await get_changes(
                table_id=None,
                grid_table_id=None,
                since_version=0,
                limit=None,
                workspace_id=None,
                session=AsyncMock(),
                current_user=SimpleNamespace(id="user-1"),
            )

        self.assertEqual(context.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
