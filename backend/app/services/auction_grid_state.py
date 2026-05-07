from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auction import AuctionLotRecord
from app.services.grid_state import bump_dataset_version


AUCTION_LOTS_TABLE_ID = "auction-lots"
DEFAULT_GRID_WORKSPACE_ID = "default"


def auction_lot_grid_row_id(record: AuctionLotRecord) -> str:
    return f"{record.source_code}:{record.auction_external_id}:{record.lot_external_id}"


async def bump_auction_lot_dataset_version(
    session: AsyncSession,
    record: AuctionLotRecord,
    *,
    event_type: str,
    payload: Mapping[str, Any] | None = None,
    workspace_id: str = DEFAULT_GRID_WORKSPACE_ID,
) -> int:
    return await bump_dataset_version(
        session,
        workspace_id,
        AUCTION_LOTS_TABLE_ID,
        event_type=event_type,
        row_id=auction_lot_grid_row_id(record),
        payload=payload,
    )
