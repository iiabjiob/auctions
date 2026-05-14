from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.infrastructure.db.database import get_db, get_read_db
from app.models import UserModel
from app.schemas.grid_history import GridHistoryMutationRequest, GridHistoryMutationResponse, GridHistoryStatusResponse
from app.services.auction_grid_state import DEFAULT_GRID_WORKSPACE_ID
from app.services.grid_backend_history import get_grid_history_status as get_grid_history_status_service
from app.services.grid_backend_history import redo_grid_history as redo_grid_history_service
from app.services.grid_backend_history import undo_grid_history as undo_grid_history_service


router = APIRouter(prefix="/api/history", tags=["Grid History"])


@router.post("/undo", response_model=GridHistoryMutationResponse)
async def undo_grid_history(
    payload: GridHistoryMutationRequest,
    workspace_id: str | None = Header(default=None, alias="X-Workspace-Id"),
    session: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> GridHistoryMutationResponse:
    try:
        response = await undo_grid_history_service(
            session,
            workspace_id=workspace_id or DEFAULT_GRID_WORKSPACE_ID,
            table_id=payload.table_id,
            user_id=_resolve_history_user_id(payload.user_id, current_user),
            session_id=payload.session_id,
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


@router.post("/redo", response_model=GridHistoryMutationResponse)
async def redo_grid_history(
    payload: GridHistoryMutationRequest,
    workspace_id: str | None = Header(default=None, alias="X-Workspace-Id"),
    session: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> GridHistoryMutationResponse:
    try:
        response = await redo_grid_history_service(
            session,
            workspace_id=workspace_id or DEFAULT_GRID_WORKSPACE_ID,
            table_id=payload.table_id,
            user_id=_resolve_history_user_id(payload.user_id, current_user),
            session_id=payload.session_id,
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


@router.get("/status", response_model=GridHistoryStatusResponse)
async def get_grid_history_status(
    table_id: str = Query(alias="tableId", min_length=1),
    user_id: str | None = Query(default=None, alias="userId"),
    session_id: str | None = Query(default=None, alias="sessionId"),
    workspace_id: str | None = Header(default=None, alias="X-Workspace-Id"),
    session: AsyncSession = Depends(get_read_db),
    current_user: UserModel = Depends(get_current_user),
) -> GridHistoryStatusResponse:
    try:
        return await get_grid_history_status_service(
            session,
            workspace_id=workspace_id or DEFAULT_GRID_WORKSPACE_ID,
            table_id=table_id,
            user_id=_resolve_history_user_id(user_id, current_user),
            session_id=session_id,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/status", response_model=GridHistoryStatusResponse)
async def post_grid_history_status(
    payload: GridHistoryMutationRequest,
    workspace_id: str | None = Header(default=None, alias="X-Workspace-Id"),
    session: AsyncSession = Depends(get_read_db),
    current_user: UserModel = Depends(get_current_user),
) -> GridHistoryStatusResponse:
    try:
        return await get_grid_history_status_service(
            session,
            workspace_id=workspace_id or DEFAULT_GRID_WORKSPACE_ID,
            table_id=payload.table_id,
            user_id=_resolve_history_user_id(payload.user_id, current_user),
            session_id=payload.session_id,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


def _resolve_history_user_id(request_user_id: str | None, current_user: UserModel) -> str:
    if request_user_id is not None and request_user_id.strip() and request_user_id.strip() != current_user.id:
        raise HTTPException(status_code=403, detail="Cannot access another user's grid history")
    return current_user.id
