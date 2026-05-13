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
)
from app.services.procurement_catalog import list_procurement_lots
from app.services.procurement_sync import sync_zakupki_procurements
from app.services.zakupki_scraper import source_info


router = APIRouter(prefix="/api/v1/procurements", tags=["Procurements"])


@router.get("/sources", response_model=list[ProcurementSourceInfo])
async def get_procurement_sources(
    current_user: UserModel = Depends(get_current_user),
) -> list[ProcurementSourceInfo]:
    return [source_info()]


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
    limit: int | None = Query(default=100, ge=1, le=1000),
    session: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> ProcurementSyncResult:
    try:
        return await sync_zakupki_procurements(session, limit=limit)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
