from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.database import get_db
from app.schemas.auction_pipeline_observability import AuctionPipelineHealthResponse
from app.services.auction_pipeline_observability import get_auction_pipeline_counters


router = APIRouter(prefix="/api/v1/health", tags=["Health"])


@router.get("/auction-pipeline", response_model=AuctionPipelineHealthResponse)
async def get_auction_pipeline_health(session: AsyncSession = Depends(get_db)) -> AuctionPipelineHealthResponse:
    return await get_auction_pipeline_counters(session)
