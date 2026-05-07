from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.infrastructure.db.database import get_db
from app.models import UserModel
from app.schemas.auction_grid import (
    AuctionLotsGridHistogramRequest,
    AuctionLotsGridHistogramResponse,
    AuctionLotsGridPullRequest,
    AuctionLotsGridPullResponse,
)
from app.services.auction_grid import DEFAULT_GRID_WORKSPACE_ID, get_auction_lots_grid_histogram, pull_auction_lots_grid


router = APIRouter(prefix="/api/auction-lots", tags=["Auction Lots Grid"])


@router.post("/pull", response_model=AuctionLotsGridPullResponse)
async def pull_auction_lots(
    payload: AuctionLotsGridPullRequest,
    workspace_id: str | None = Header(default=None, alias="X-Workspace-Id"),
    session: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> AuctionLotsGridPullResponse:
    del current_user
    try:
        return await pull_auction_lots_grid(
            session,
            payload,
            workspace_id=workspace_id or DEFAULT_GRID_WORKSPACE_ID,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/histogram", response_model=AuctionLotsGridHistogramResponse)
async def get_auction_lots_histogram(
    payload: AuctionLotsGridHistogramRequest,
    session: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> AuctionLotsGridHistogramResponse:
    del current_user
    try:
        return await get_auction_lots_grid_histogram(session, payload)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
