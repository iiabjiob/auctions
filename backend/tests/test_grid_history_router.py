from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, patch

from app.api.grid_history_router import post_grid_history_status
from app.schemas.grid_history import GridHistoryMutationRequest
from app.schemas.grid_history import GridHistoryStatusResponse
from app.services.procurement_grid_state import DEFAULT_GRID_WORKSPACE_ID, PROCUREMENT_LOTS_TABLE_ID


class GridHistoryRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_post_history_status_uses_body_scope_for_package_adapter(self) -> None:
        request = GridHistoryMutationRequest(
            tableId=PROCUREMENT_LOTS_TABLE_ID,
            userId=None,
            sessionId="session-1",
        )

        with patch(
            "app.api.grid_history_router.get_grid_history_status_service",
            AsyncMock(return_value=GridHistoryStatusResponse(canUndo=True, canRedo=False)),
        ) as status_service:
            response = await post_grid_history_status(
                request,
                workspace_id=None,
                session=AsyncMock(),
                current_user=SimpleNamespace(id="user-1"),
            )

        self.assertTrue(response.can_undo)
        self.assertFalse(response.can_redo)
        status_service.assert_awaited_once_with(
            ANY,
            workspace_id=DEFAULT_GRID_WORKSPACE_ID,
            table_id=PROCUREMENT_LOTS_TABLE_ID,
            user_id="user-1",
            session_id="session-1",
        )


if __name__ == "__main__":
    unittest.main()
