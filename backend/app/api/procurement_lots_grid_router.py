from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.infrastructure.db.database import get_db, get_read_db
from app.models import UserModel
from app.schemas.procurement_grid import (
    ProcurementLotsGridEditRequest,
    ProcurementLotsGridEditResponse,
    ProcurementLotsGridFillRequest,
    ProcurementLotsGridHistogramRequest,
    ProcurementLotsGridHistogramResponse,
    ProcurementLotsGridPullRequest,
    ProcurementLotsGridPullResponse,
)
from app.services.procurement_grid import get_procurement_lots_grid_histogram, pull_procurement_lots_grid
from app.services.procurement_grid_edits import ProcurementGridEditConflictError, commit_procurement_lot_grid_edits
from app.services.procurement_grid_fill import commit_procurement_lot_grid_fill
from app.services.procurement_grid_state import DEFAULT_GRID_WORKSPACE_ID


router = APIRouter(prefix="/api/procurement-lots", tags=["Procurement Lots Grid"])


@router.post("/pull", response_model=ProcurementLotsGridPullResponse)
async def pull_procurement_lots(
    payload: ProcurementLotsGridPullRequest,
    workspace_id: str | None = Header(default=None, alias="X-Workspace-Id"),
    session: AsyncSession = Depends(get_read_db),
    current_user: UserModel = Depends(get_current_user),
) -> ProcurementLotsGridPullResponse:
    del current_user
    try:
        return await pull_procurement_lots_grid(
            session,
            payload,
            workspace_id=workspace_id or DEFAULT_GRID_WORKSPACE_ID,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/histogram", response_model=ProcurementLotsGridHistogramResponse)
async def get_procurement_lots_histogram(
    payload: ProcurementLotsGridHistogramRequest,
    session: AsyncSession = Depends(get_read_db),
    current_user: UserModel = Depends(get_current_user),
) -> ProcurementLotsGridHistogramResponse:
    del current_user
    try:
        return await get_procurement_lots_grid_histogram(session, payload)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/edits", response_model=ProcurementLotsGridEditResponse)
async def commit_procurement_lots_edits(
    payload: ProcurementLotsGridEditRequest,
    workspace_id: str | None = Header(default=None, alias="X-Workspace-Id"),
    grid_session_id: str | None = Header(default=None, alias="X-Grid-Session-Id"),
    session: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> ProcurementLotsGridEditResponse:
    try:
        response = await commit_procurement_lot_grid_edits(
            session,
            payload,
            workspace_id=workspace_id or DEFAULT_GRID_WORKSPACE_ID,
            user_id=current_user.id,
            session_id=grid_session_id,
        )
        await session.commit()
        return response
    except ProcurementGridEditConflictError as error:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail={"message": str(error), "currentDatasetVersion": error.current_version},
        ) from error
    except ValueError as error:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(error)) from error
    except LookupError as error:
        await session.rollback()
        raise HTTPException(status_code=404, detail=str(error)) from error
    except Exception:
        await session.rollback()
        raise


@router.post("/fill", response_model=ProcurementLotsGridEditResponse)
async def commit_procurement_lots_fill(
    payload: ProcurementLotsGridFillRequest,
    workspace_id: str | None = Header(default=None, alias="X-Workspace-Id"),
    grid_session_id: str | None = Header(default=None, alias="X-Grid-Session-Id"),
    session: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> ProcurementLotsGridEditResponse:
    try:
        response = await commit_procurement_lot_grid_fill(
            session,
            payload,
            workspace_id=workspace_id or DEFAULT_GRID_WORKSPACE_ID,
            user_id=current_user.id,
            session_id=grid_session_id,
        )
        await session.commit()
        return response
    except ProcurementGridEditConflictError as error:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail={"message": str(error), "currentDatasetVersion": error.current_version},
        ) from error
    except ValueError as error:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(error)) from error
    except LookupError as error:
        await session.rollback()
        raise HTTPException(status_code=404, detail=str(error)) from error
    except Exception:
        await session.rollback()
        raise
