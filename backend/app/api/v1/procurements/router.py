from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.infrastructure.db.database import get_db, get_read_db
from app.models import UserModel
from app.schemas.procurements import (
    ProcurementLotListResponse,
    ProcurementSourceInfo,
    ProcurementSyncResult,
    ProcurementWorkspaceRefreshResponse,
    ProcurementWorkspaceResponse,
)
from app.services.procurement_catalog import list_procurement_lots
from app.services.procurement_sources import list_procurement_source_infos
from app.services.procurement_sync import sync_procurement_source
from app.services.procurement_workspace import get_procurement_lot_workspace, refresh_procurement_lot_workspace_live


router = APIRouter(prefix="/api/v1/procurements", tags=["Procurements"])


@router.get("/sources", response_model=list[ProcurementSourceInfo])
async def get_procurement_sources(
    current_user: UserModel = Depends(get_current_user),
) -> list[ProcurementSourceInfo]:
    del current_user
    return list_procurement_source_infos()


@router.get("/lots", response_model=ProcurementLotListResponse)
async def get_procurement_lots(
    source: str | None = Query(default="zakupki"),
    law: str | None = Query(default=None),
    status: str | None = Query(default=None),
    min_price: Decimal | None = Query(default=None, ge=0),
    max_price: Decimal | None = Query(default=None, ge=0),
    min_score: int | None = Query(default=None, ge=0, le=100),
    only_new: bool = Query(default=False),
    search: str | None = Query(default=None, min_length=2),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=1000),
    session: AsyncSession = Depends(get_read_db),
    current_user: UserModel = Depends(get_current_user),
) -> ProcurementLotListResponse:
    return await list_procurement_lots(
        session,
        source=source,
        law=law,
        status=status,
        min_price=min_price,
        max_price=max_price,
        min_score=min_score,
        only_new=only_new,
        search=search,
        page=page,
        page_size=page_size,
    )


@router.post("/sync", response_model=ProcurementSyncResult)
async def sync_procurements(
    source: str = Query(default="zakupki"),
    limit: int | None = Query(default=100, ge=1, le=1000),
    session: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> ProcurementSyncResult:
    del current_user
    try:
        return await sync_procurement_source(session, source=source, limit=limit)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/{source}/lots/{external_id}/workspace", response_model=ProcurementWorkspaceResponse)
async def get_procurement_workspace(
    source: str,
    external_id: str,
    refresh: bool = Query(default=False),
    include_detail: bool = Query(default=True),
    session: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> ProcurementWorkspaceResponse:
    del current_user
    try:
        return await get_procurement_lot_workspace(
            session,
            source=source,
            external_id=external_id,
            refresh=refresh,
            include_detail=include_detail,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/{source}/lots/{external_id}/workspace/refresh", response_model=ProcurementWorkspaceRefreshResponse)
async def refresh_procurement_workspace(
    source: str,
    external_id: str,
    session: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> ProcurementWorkspaceRefreshResponse:
    del current_user
    try:
        return await refresh_procurement_lot_workspace_live(session, source=source, external_id=external_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
