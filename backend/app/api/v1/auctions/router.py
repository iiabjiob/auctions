from __future__ import annotations

import asyncio
import json
from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.infrastructure.db.database import get_db
from app.models import UserModel
from app.schemas.analysis_config import AuctionAnalysisConfigResponse, AuctionAnalysisConfigUpdate
from app.schemas.auctions import (
    AuctionDetailResponse,
    AuctionListResponse,
    AuctionSourceInfo,
    LotDatagridResponse,
    LotDetailResponse,
    LotWorkItemUpdate,
    LotWorkspaceResponse,
)
from app.services.auction_catalog import list_lots_for_datagrid, list_persisted_lots_for_datagrid
from app.services.auction_analysis_config import auction_analysis_config_service
from app.services.auction_sources import get_source_provider, list_source_infos
from app.services.auction_workspace import get_lot_workspace, update_lot_work_item
from app.infrastructure.redis.streams import read_auction_events
from app.services.utender_scraper import (
    fetch_auction_detail,
    fetch_auction_list,
    fetch_lot_detail,
)


router = APIRouter(prefix="/api/v1/auctions", tags=["Auctions"])


def _format_sse(event: dict) -> str:
    event_type = event.get("type", "message")
    event_id = event.get("id")
    payload = json.dumps(event, ensure_ascii=False)
    if event_id:
        return f"id: {event_id}\nevent: {event_type}\ndata: {payload}\n\n"
    return f"event: {event_type}\ndata: {payload}\n\n"


@router.get("/sources", response_model=list[AuctionSourceInfo])
async def get_auction_sources() -> list[AuctionSourceInfo]:
    return list_source_infos()


@router.get("/analysis-config", response_model=AuctionAnalysisConfigResponse)
async def get_auction_analysis_config(
    session: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> AuctionAnalysisConfigResponse:
    return await auction_analysis_config_service.get(session)


@router.patch("/analysis-config", response_model=AuctionAnalysisConfigResponse)
async def patch_auction_analysis_config(
    payload: AuctionAnalysisConfigUpdate,
    session: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> AuctionAnalysisConfigResponse:
    return await auction_analysis_config_service.update(session, payload)


@router.get("/lots", response_model=LotDatagridResponse)
async def get_lots_datagrid(
    period: str = Query(default="month", pattern="^(week|month|year)$"),
    source: str | None = Query(default=None),
    q: str | None = Query(default=None),
    status: str | None = Query(default=None),
    min_price: Decimal | None = Query(default=None, ge=0),
    max_price: Decimal | None = Query(default=None, ge=0),
    only_new: bool = Query(default=False),
    shortlist: bool = Query(default=False),
    min_rating: int | None = Query(default=None, ge=0, le=100),
    persisted: bool = Query(default=True),
    page: int = Query(default=1, ge=1),
    page_size: int | None = Query(default=None, ge=1, le=10000),
    limit: int | None = Query(default=None, ge=1, le=10000),
    session: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> LotDatagridResponse:
    resolved_page_size = page_size or limit or 100
    try:
        if persisted:
            return await list_persisted_lots_for_datagrid(
                session,
                period=period,
                source=source,
                q=q,
                status=status,
                min_price=min_price,
                max_price=max_price,
                only_new=only_new,
                shortlist=shortlist,
                min_rating=min_rating,
                page=page,
                page_size=resolved_page_size,
            )
        return await asyncio.to_thread(
            list_lots_for_datagrid,
            period=period,
            source=source,
            q=q,
            status=status,
            min_price=min_price,
            max_price=max_price,
            only_new=only_new,
            shortlist=shortlist,
            min_rating=min_rating,
            page=page,
            page_size=resolved_page_size,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/events")
async def stream_auction_events(
    last_id: str = Query(default="$"),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    async def event_stream():
        async for event in read_auction_events(last_id=last_event_id or last_id):
            yield _format_sse(event)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/{source}/lots/{lot_id}", response_model=LotDetailResponse)
async def get_source_lot(
    source: str,
    lot_id: str,
    current_user: UserModel = Depends(get_current_user),
) -> LotDetailResponse:
    try:
        provider = get_source_provider(source)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return await asyncio.to_thread(provider.get_lot, lot_id)


@router.get("/{source}/lots/{lot_id}/workspace", response_model=LotWorkspaceResponse)
async def get_source_lot_workspace(
    source: str,
    lot_id: str,
    auction_id: str | None = Query(default=None),
    refresh: bool = Query(default=False),
    session: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> LotWorkspaceResponse:
    try:
        return await get_lot_workspace(session, source=source, lot_id=lot_id, auction_id=auction_id, refresh=refresh)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.patch("/{source}/lots/{lot_id}/workspace", response_model=LotWorkspaceResponse)
async def patch_source_lot_workspace(
    source: str,
    lot_id: str,
    payload: LotWorkItemUpdate,
    auction_id: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> LotWorkspaceResponse:
    try:
        return await update_lot_work_item(session, source=source, lot_id=lot_id, auction_id=auction_id, payload=payload)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/{source}/{auction_id}", response_model=AuctionDetailResponse)
async def get_source_auction(
    source: str,
    auction_id: str,
    current_user: UserModel = Depends(get_current_user),
) -> AuctionDetailResponse:
    try:
        provider = get_source_provider(source)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return await asyncio.to_thread(provider.get_auction, auction_id)


@router.get("/utender", response_model=AuctionListResponse)
async def get_utender_auctions(
    limit: int = Query(default=20, ge=1, le=100),
    current_user: UserModel = Depends(get_current_user),
) -> AuctionListResponse:
    items = await asyncio.to_thread(fetch_auction_list, limit)
    return AuctionListResponse(items=items)


@router.get("/utender/lots/{lot_id}", response_model=LotDetailResponse)
async def get_utender_lot(
    lot_id: str,
    current_user: UserModel = Depends(get_current_user),
) -> LotDetailResponse:
    return await asyncio.to_thread(fetch_lot_detail, lot_id)


@router.get("/utender/{auction_id}", response_model=AuctionDetailResponse)
async def get_utender_auction(
    auction_id: str,
    current_user: UserModel = Depends(get_current_user),
) -> AuctionDetailResponse:
    return await asyncio.to_thread(fetch_auction_detail, auction_id)
