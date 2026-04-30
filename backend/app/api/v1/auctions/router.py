from __future__ import annotations

import asyncio
import json
import logging
from decimal import Decimal
from urllib.error import HTTPError, URLError

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.infrastructure.db.database import AsyncSessionLocal, get_db
from app.models import UserModel
from app.schemas.analysis_config import AuctionAnalysisConfigResponse, AuctionAnalysisConfigUpdate
from app.schemas.auctions import (
    AuctionDetailResponse,
    AuctionSourceInfo,
    LotDatagridResponse,
    LotDatagridHistogramEntry,
    LotDatagridHistogramRequest,
    LotDetailResponse,
    LotWorkItemUpdate,
    LotWorkspaceRefreshResponse,
    LotWorkspaceResponse,
)
from app.services.auction_catalog import list_lots_for_datagrid, list_persisted_lots_for_datagrid, list_persisted_lot_column_histogram
from app.services.auction_analysis_config import auction_analysis_config_service
from app.services.auction_sources import get_source_provider, list_source_infos
from app.services.auction_workspace import find_lot_record, get_lot_workspace, refresh_lot_workspace_live, update_lot_work_item
from app.infrastructure.redis.streams import publish_auction_event, read_auction_events


router = APIRouter(prefix="/api/v1/auctions", tags=["Auctions"])
logger = logging.getLogger(__name__)
_LIVE_WORKSPACE_REFRESH_TASKS: set[tuple[str, str, str | None]] = set()


def _format_sse(event: dict) -> str:
    event_type = event.get("type", "message")
    event_id = event.get("id")
    payload = json.dumps(event, ensure_ascii=False)
    if event_id:
        return f"id: {event_id}\nevent: {event_type}\ndata: {payload}\n\n"
    return f"event: {event_type}\ndata: {payload}\n\n"


async def _refresh_lot_workspace_background(source: str, lot_id: str, auction_id: str | None) -> None:
    key = (source, lot_id, auction_id)
    try:
        logger.info(
            "Background lot workspace live refresh started",
            extra={"source_code": source, "lot_id": lot_id, "auction_id": auction_id},
        )
        async with AsyncSessionLocal() as session:
            await refresh_lot_workspace_live(session, source=source, lot_id=lot_id, auction_id=auction_id)
        logger.info(
            "Background lot workspace live refresh completed",
            extra={"source_code": source, "lot_id": lot_id, "auction_id": auction_id},
        )
    except Exception as error:
        payload = _lot_detail_refresh_error_payload(source=source, lot_id=lot_id, auction_id=auction_id, error=error)
        if payload["expected"]:
            logger.warning(
                "Background lot workspace live refresh failed: %s",
                payload["message"],
                extra={
                    "source_code": source,
                    "lot_id": lot_id,
                    "auction_id": auction_id,
                    "error_code": payload["error_code"],
                    "http_status": payload.get("http_status"),
                },
            )
        else:
            logger.exception(
                "Background lot workspace live refresh failed",
                extra={"source_code": source, "lot_id": lot_id, "auction_id": auction_id},
            )
        await publish_auction_event(
            "lot.detail_refresh_failed",
            {key: value for key, value in payload.items() if key != "expected"},
        )
    finally:
        _LIVE_WORKSPACE_REFRESH_TASKS.discard(key)


def _lot_detail_refresh_error_payload(
    *,
    source: str,
    lot_id: str,
    auction_id: str | None,
    error: Exception,
) -> dict:
    payload = {
        "source": source,
        "lot_id": lot_id,
        "auction_id": auction_id,
        "error_code": "unexpected_error",
        "message": "Live refresh failed unexpectedly",
        "retryable": False,
        "expected": False,
    }
    if isinstance(error, HTTPError):
        payload["http_status"] = error.code
        payload["expected"] = True
        if error.code == 403:
            payload["error_code"] = "source_forbidden"
            payload["message"] = "Source returned 403 Forbidden"
            payload["retryable"] = False
        elif error.code == 429:
            payload["error_code"] = "source_rate_limited"
            payload["message"] = "Source rate limit reached"
            payload["retryable"] = True
        else:
            payload["error_code"] = "source_http_error"
            payload["message"] = f"Source returned HTTP {error.code}"
            payload["retryable"] = 500 <= error.code < 600
        return payload
    if isinstance(error, TimeoutError):
        payload["error_code"] = "source_timeout"
        payload["message"] = "Source request timed out"
        payload["retryable"] = True
        payload["expected"] = True
        return payload
    if isinstance(error, URLError):
        payload["error_code"] = "source_network_error"
        payload["message"] = str(error.reason) if getattr(error, "reason", None) else "Could not connect to source"
        payload["retryable"] = True
        payload["expected"] = True
        return payload
    if isinstance(error, OSError):
        payload["error_code"] = "source_io_error"
        payload["message"] = str(error) or "Source read failed"
        payload["retryable"] = True
        payload["expected"] = True
        return payload
    payload["message"] = str(error) or payload["message"]
    return payload


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
    source: str | None = Query(default="tbankrot"),
    q: str | None = Query(default=None),
    status: str | None = Query(default=None),
    analysis_color: str | None = Query(default=None),
    min_price: Decimal | None = Query(default=None, ge=0),
    max_price: Decimal | None = Query(default=None, ge=0),
    only_new: bool = Query(default=False),
    shortlist: bool = Query(default=False),
    min_rating: int | None = Query(default=None, ge=0, le=100),
    persisted: bool = Query(default=True),
    page: int = Query(default=1, ge=1),
    page_size: int | None = Query(default=None, ge=1, le=10000),
    offset: int | None = Query(default=None, ge=0),
    limit: int | None = Query(default=None, ge=1, le=10000),
    sort_by: str | None = Query(default=None),
    sort_direction: str = Query(default="asc", pattern="^(asc|desc)$"),
    sort_model: str | None = Query(default=None),
    grid_filter: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> LotDatagridResponse:
    resolved_page_size = page_size or limit or 100
    try:
        parsed_sort_model = _parse_sort_model(sort_model)
        parsed_grid_filter = _parse_grid_filter(grid_filter)
        if persisted:
            return await list_persisted_lots_for_datagrid(
                session,
                period=period,
                source=source,
                q=q,
                status=status,
                analysis_color=analysis_color,
                min_price=min_price,
                max_price=max_price,
                only_new=only_new,
                shortlist=shortlist,
                min_rating=min_rating,
                page=page,
                page_size=resolved_page_size,
                offset=offset,
                sort_by=sort_by,
                sort_direction=sort_direction,
                sort_model=parsed_sort_model,
                grid_filter=parsed_grid_filter,
            )
        return await asyncio.to_thread(
            list_lots_for_datagrid,
            period=period,
            source=source,
            q=q,
            status=status,
            analysis_color=analysis_color,
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


@router.post("/lots/histogram", response_model=list[LotDatagridHistogramEntry])
async def get_lots_column_histogram(
    payload: LotDatagridHistogramRequest,
    session: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> list[LotDatagridHistogramEntry]:
    try:
        return await list_persisted_lot_column_histogram(
            session,
            period=payload.period,
            source=payload.source,
            q=payload.q,
            status=payload.status,
            analysis_color=payload.analysis_color,
            min_price=payload.min_price,
            max_price=payload.max_price,
            only_new=payload.only_new,
            shortlist=payload.shortlist,
            min_rating=payload.min_rating,
            column_id=payload.column_id,
            histogram_options=payload.options,
            sort_model=payload.sort_model,
            grid_filter=payload.grid_filter,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


def _parse_grid_filter(payload: str | None) -> dict | None:
    if not payload:
        return None
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as error:
        raise ValueError("Invalid grid_filter JSON") from error
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("grid_filter must be a JSON object")
    return value


def _parse_sort_model(payload: str | None) -> list[dict] | None:
    if not payload:
        return None
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as error:
        raise ValueError("Invalid sort_model JSON") from error
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError("sort_model must be a JSON array")
    normalized: list[dict] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        direction = item.get("direction", "asc")
        if not isinstance(key, str) or direction not in {"asc", "desc"}:
            continue
        normalized.append({"key": key, "direction": direction})
    return normalized or None


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
    include_detail: bool = Query(default=True),
    session: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> LotWorkspaceResponse:
    try:
        return await get_lot_workspace(
            session,
            source=source,
            lot_id=lot_id,
            auction_id=auction_id,
            refresh=refresh,
            include_detail=include_detail,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/{source}/lots/{lot_id}/workspace/refresh", response_model=LotWorkspaceRefreshResponse, status_code=202)
async def queue_source_lot_workspace_refresh(
    source: str,
    lot_id: str,
    background_tasks: BackgroundTasks,
    auction_id: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> LotWorkspaceRefreshResponse:
    try:
        get_source_provider(source)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    record = await find_lot_record(session, source=source, lot_id=lot_id, auction_id=auction_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Lot record was not found in persisted catalog")

    key = (source, lot_id, auction_id)
    if key in _LIVE_WORKSPACE_REFRESH_TASKS:
        return LotWorkspaceRefreshResponse(status="already_running", queued=False)

    _LIVE_WORKSPACE_REFRESH_TASKS.add(key)
    background_tasks.add_task(_refresh_lot_workspace_background, source, lot_id, auction_id)
    return LotWorkspaceRefreshResponse(status="queued", queued=True)


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
