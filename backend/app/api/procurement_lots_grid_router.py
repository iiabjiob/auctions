from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.infrastructure.db.database import get_db, get_read_db
from app.models import UserModel
from app.schemas.procurement_grid import (
    ProcurementLotsGridFillCommitRequest,
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
from app.services.procurement_grid_fill import commit_procurement_lot_grid_fill, commit_procurement_lot_grid_fill_commit
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


@router.post("/fill/commit")
async def commit_procurement_lots_fill_commit(
    payload: ProcurementLotsGridFillCommitRequest,
    workspace_id: str | None = Header(default=None, alias="X-Workspace-Id"),
    grid_session_id: str | None = Header(default=None, alias="X-Grid-Session-Id"),
    session: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> dict[str, object]:
    try:
        response = await commit_procurement_lot_grid_fill_commit(
            session,
            payload,
            workspace_id=workspace_id or payload.workspace_id or DEFAULT_GRID_WORKSPACE_ID,
            user_id=_resolve_grid_user_id(payload.user_id, current_user),
            session_id=grid_session_id or payload.session_id,
        )
        await session.commit()
        row_ids = [row.id for row in response.updated_rows]
        return {
            "operationId": payload.operation_id,
            "revision": str(response.dataset_version),
            "datasetVersion": response.dataset_version,
            "updatedRows": [row.model_dump(by_alias=True) for row in response.updated_rows],
            "rows": [row.model_dump(by_alias=True) for row in response.updated_rows],
            "affectedRowCount": len(row_ids),
            "affectedCellCount": len(row_ids) * max(1, len(payload.fill_columns)),
            "invalidation": {"type": "rows", "rowIds": row_ids, "reason": "fill"},
            "warnings": [],
        }
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


@router.post("/fill-boundary")
async def resolve_procurement_lots_fill_boundary(
    payload: dict[str, object],
    current_user: UserModel = Depends(get_current_user),
) -> dict[str, object | None]:
    del payload, current_user
    return {"boundaryKind": "unresolved", "endRowIndex": None}


def _resolve_grid_user_id(request_user_id: str | None, current_user: UserModel) -> str:
    if request_user_id is not None and request_user_id.strip() and request_user_id.strip() != current_user.id:
        raise HTTPException(status_code=403, detail="Cannot access another user's grid history")
    return current_user.id
