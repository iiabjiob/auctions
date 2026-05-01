from __future__ import annotations

import unittest
from unittest.mock import patch

from app.schemas.auctions import (
    LotChangeSummary,
    LotDatagridRow,
    LotEconomyResponse,
    LotFreshness,
    LotRating,
    LotWorkItemResponse,
    LotWorkItemUpdate,
    LotWorkspaceBatchCommitItem,
    LotWorkspaceResponse,
)
from app.services.auction_workspace import batch_update_lot_work_items


class FakeSession:
    async def rollback(self) -> None:
        return None


def build_workspace_response(lot_id: str, row_id: str | None = None) -> LotWorkspaceResponse:
    resolved_row_id = row_id or f"row-{lot_id}"
    return LotWorkspaceResponse(
        record_id=1,
        row=LotDatagridRow(
            row_id=resolved_row_id,
            source="tbankrot",
            source_title="TBankrot",
            lot_id=lot_id,
            freshness=LotFreshness(),
            rating=LotRating(score=0, level="low", reasons=[]),
        ),
        work_item=LotWorkItemResponse(lot_record_id=1),
        economy=LotEconomyResponse(),
        changes=LotChangeSummary(),
    )


class AuctionWorkspaceBatchCommitTests(unittest.IsolatedAsyncioTestCase):
    async def test_batch_commit_returns_committed_and_rejected_rows(self) -> None:
        async def fake_update_lot_work_item(session, *, source, lot_id, auction_id=None, payload):
            if lot_id == "rejected":
                raise LookupError("Lot record was not found in persisted catalog")
            return build_workspace_response(lot_id)

        request = [
            LotWorkspaceBatchCommitItem(
                source="tbankrot",
                lot_id="accepted",
                auction_id="auction-1",
                payload=LotWorkItemUpdate(comment="ok"),
            ),
            LotWorkspaceBatchCommitItem(
                source="tbankrot",
                lot_id="rejected",
                auction_id="auction-2",
                payload=LotWorkItemUpdate(comment="fail"),
            ),
        ]

        with patch("app.services.auction_workspace.update_lot_work_item", side_effect=fake_update_lot_work_item):
            result = await batch_update_lot_work_items(FakeSession(), updates=request)

        self.assertEqual(len(result.committed), 1)
        self.assertEqual(len(result.rejected), 1)
        self.assertEqual(result.committed[0].lot_id, "accepted")
        self.assertEqual(result.committed[0].workspace.row.lot_id, "accepted")
        self.assertEqual(result.rejected[0].lot_id, "rejected")
        self.assertIn("not found", result.rejected[0].error)


if __name__ == "__main__":
    unittest.main()
