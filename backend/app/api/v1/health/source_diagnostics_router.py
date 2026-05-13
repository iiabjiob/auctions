from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.database import get_db
from app.schemas.source_diagnostics import DiagnosticsRange, SourceDiagnosticsResponse
from app.services.source_http_diagnostics import get_source_diagnostics


router = APIRouter(prefix="/api/v1/health", tags=["Health"])


@router.get("/source-diagnostics", response_model=SourceDiagnosticsResponse)
async def get_source_exchange_diagnostics(
    range: DiagnosticsRange = Query(default="day"),
    session: AsyncSession = Depends(get_db),
) -> SourceDiagnosticsResponse:
    return await get_source_diagnostics(session, range_name=range)
