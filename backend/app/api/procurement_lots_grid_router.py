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
from app.services.procurement_grid_state import PROCUREMENT_LOTS_TABLE_ID
from app.services.grid_backend_history import redo_grid_operation, undo_grid_operation
from app.services.grid_state import get_dataset_version


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
        await session.rollback()
        return response
    except ProcurementGridEditConflictError as error:
        await session.rollback()
        return _procurement_rejected_edit_response(payload, dataset_version=error.current_version, reason=str(error))
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
        return _procurement_rejected_edit_response(
            ProcurementLotsGridEditRequest(
                baseVersion=payload.base_version,
                edits=[{"rowId": "", "columnId": payload.target.column_id, "value": None}],
            ),
            dataset_version=error.current_version,
            reason=str(error),
        )
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
        return _procurement_rejected_fill_response(payload, dataset_version=error.current_version, reason=str(error))
    except ValueError as error:
        await session.rollback()
        version = await get_dataset_version(session, workspace_id or DEFAULT_GRID_WORKSPACE_ID, PROCUREMENT_LOTS_TABLE_ID)
        return _procurement_rejected_history_response(operation_id, action="undo", dataset_version=version, reason=str(error))
    except LookupError as error:
        await session.rollback()
        version = await get_dataset_version(session, workspace_id or DEFAULT_GRID_WORKSPACE_ID, PROCUREMENT_LOTS_TABLE_ID)
        return _procurement_rejected_history_response(operation_id, action="undo", dataset_version=version, reason=str(error))
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


@router.post("/operations/{operation_id}/undo")
async def undo_procurement_lot_grid_operation(
    operation_id: str,
    workspace_id: str | None = Header(default=None, alias="X-Workspace-Id"),
    grid_session_id: str | None = Header(default=None, alias="X-Grid-Session-Id"),
    session: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    try:
        response = await undo_grid_operation(
            session,
            workspace_id=workspace_id or DEFAULT_GRID_WORKSPACE_ID,
            table_id="procurement-lots",
            operation_id=operation_id,
            user_id=current_user.id,
            session_id=grid_session_id,
        )
        await session.commit()
        return response
    except ValueError as error:
        await session.rollback()
        version = await get_dataset_version(session, workspace_id or DEFAULT_GRID_WORKSPACE_ID, PROCUREMENT_LOTS_TABLE_ID)
        return _procurement_rejected_history_response(operation_id, action="redo", dataset_version=version, reason=str(error))
    except LookupError as error:
        await session.rollback()
        version = await get_dataset_version(session, workspace_id or DEFAULT_GRID_WORKSPACE_ID, PROCUREMENT_LOTS_TABLE_ID)
        return _procurement_rejected_history_response(operation_id, action="redo", dataset_version=version, reason=str(error))
    except Exception:
        await session.rollback()
        raise


def _procurement_rejected_edit_response(
    payload: ProcurementLotsGridEditRequest,
    *,
    dataset_version: int,
    reason: str,
) -> ProcurementLotsGridEditResponse:
    return ProcurementLotsGridEditResponse(
        datasetVersion=dataset_version,
        updatedRows=[],
        revision=str(dataset_version),
        committed=[],
        rejected=[
            {"rowId": edit.row_id, "columnId": edit.column_id, "reason": reason}
            for edit in payload.edits
        ],
        invalidation={"type": "dataset", "reason": "edit_rejected"},
        rows=[],
    )


def _procurement_rejected_fill_response(
    payload: ProcurementLotsGridFillCommitRequest,
    *,
    dataset_version: int,
    reason: str,
) -> dict[str, object]:
    return {
        "operationId": payload.operation_id,
        "revision": str(dataset_version),
        "datasetVersion": dataset_version,
        "updatedRows": [],
        "rows": [],
        "committed": [],
        "rejected": [
            {"rowId": row_id, "columnId": column_id, "reason": reason}
            for row_id in payload.target_row_ids
            for column_id in payload.fill_columns
        ],
        "affectedRowCount": 0,
        "affectedCellCount": 0,
        "invalidation": {"type": "dataset", "reason": "fill_rejected"},
        "warnings": [],
    }


def _procurement_rejected_history_response(
    operation_id: str,
    *,
    action: str,
    dataset_version: int,
    reason: str,
) -> dict[str, object]:
    return {
        "operationId": operation_id,
        "action": action,
        "revision": str(dataset_version),
        "datasetVersion": dataset_version,
        "updatedRows": [],
        "rows": [],
        "committed": [],
        "rejected": [{"rowId": operation_id, "reason": reason}],
        "affectedRows": 0,
        "affectedCells": 0,
        "invalidation": {"type": "dataset", "reason": f"history_{action}_rejected"},
    }


@router.post("/operations/{operation_id}/redo")
async def redo_procurement_lot_grid_operation(
    operation_id: str,
    workspace_id: str | None = Header(default=None, alias="X-Workspace-Id"),
    grid_session_id: str | None = Header(default=None, alias="X-Grid-Session-Id"),
    session: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    try:
        response = await redo_grid_operation(
            session,
            workspace_id=workspace_id or DEFAULT_GRID_WORKSPACE_ID,
            table_id="procurement-lots",
            operation_id=operation_id,
            user_id=current_user.id,
            session_id=grid_session_id,
        )
        await session.commit()
        return response
    except ValueError as error:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(error)) from error
    except LookupError as error:
        await session.rollback()
        raise HTTPException(status_code=404, detail=str(error)) from error
    except Exception:
        await session.rollback()
        raise
