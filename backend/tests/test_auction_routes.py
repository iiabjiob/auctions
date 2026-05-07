from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.api.v1.auctions.router import get_source_lot_workspace


class AuctionWorkspaceRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_workspace_route_defaults_to_cached_read_without_refresh(self) -> None:
        session = SimpleNamespace()
        user = SimpleNamespace(id=1)

        with patch("app.api.v1.auctions.router.get_lot_workspace", AsyncMock(return_value={"ok": True})) as get_workspace:
            result = await get_source_lot_workspace(
                source="tbankrot",
                lot_id="lot-1",
                auction_id=None,
                include_detail=True,
                session=session,
                current_user=user,
            )

        self.assertEqual(result, {"ok": True})
        kwargs = get_workspace.await_args.kwargs
        self.assertIs(kwargs["auction_id"], None)
        self.assertTrue(hasattr(kwargs["refresh"], "default"))
        self.assertFalse(kwargs["refresh"].default)
        self.assertTrue(kwargs["include_detail"])

    async def test_workspace_route_forwards_explicit_refresh_request(self) -> None:
        session = SimpleNamespace()
        user = SimpleNamespace(id=1)

        with patch("app.api.v1.auctions.router.get_lot_workspace", AsyncMock(return_value={"ok": True})) as get_workspace:
            result = await get_source_lot_workspace(
                source="tbankrot",
                lot_id="lot-1",
                refresh=True,
                include_detail=False,
                auction_id=None,
                session=session,
                current_user=user,
            )

        self.assertEqual(result, {"ok": True})
        get_workspace.assert_awaited_once_with(
            session,
            source="tbankrot",
            lot_id="lot-1",
            auction_id=None,
            refresh=True,
            include_detail=False,
        )


if __name__ == "__main__":
    unittest.main()
