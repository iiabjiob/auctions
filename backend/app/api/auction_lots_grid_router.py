from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.infrastructure.db.database import get_db, get_read_db
from app.models import UserModel
from app.schemas.auction_grid import (
    AuctionLotsGridFillCommitRequest,
    AuctionLotsGridEditRequest,
    AuctionLotsGridEditResponse,
    AuctionLotsGridFillRequest,
    AuctionLotsGridHistogramRequest,
    AuctionLotsGridHistogramResponse,
    AuctionLotsGridPullRequest,
    AuctionLotsGridPullResponse,
)
from app.services.auction_grid import get_auction_lots_grid_histogram, pull_auction_lots_grid
from app.services.auction_grid_edits import AuctionGridEditConflictError, commit_auction_lot_grid_edits
from app.services.auction_grid_fill import commit_auction_lot_grid_fill, commit_auction_lot_grid_fill_commit
from app.services.auction_grid_state import DEFAULT_GRID_WORKSPACE_ID
from app.services.grid_backend_history import redo_grid_operation, undo_grid_operation


router = APIRouter(prefix="/api/auction-lots", tags=["Auction Lots Grid"])


@router.post("/pull", response_model=AuctionLotsGridPullResponse)
async def pull_auction_lots(
    payload: AuctionLotsGridPullRequest,
    workspace_id: str | None = Header(default=None, alias="X-Workspace-Id"),
    session: AsyncSession = Depends(get_read_db),
    current_user: UserModel = Depends(get_current_user),
) -> AuctionLotsGridPullResponse:
    del current_user
    try:
        return await pull_auction_lots_grid(
            session,
            payload,
            workspace_id=workspace_id or DEFAULT_GRID_WORKSPACE_ID,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/histogram", response_model=AuctionLotsGridHistogramResponse)
async def get_auction_lots_histogram(
    payload: AuctionLotsGridHistogramRequest,
    session: AsyncSession = Depends(get_read_db),
    current_user: UserModel = Depends(get_current_user),
) -> AuctionLotsGridHistogramResponse:
    del current_user
    try:
        return await get_auction_lots_grid_histogram(session, payload)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/edits", response_model=AuctionLotsGridEditResponse)
async def commit_auction_lots_edits(
    payload: AuctionLotsGridEditRequest,
    workspace_id: str | None = Header(default=None, alias="X-Workspace-Id"),
    grid_session_id: str | None = Header(default=None, alias="X-Grid-Session-Id"),
    session: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> AuctionLotsGridEditResponse:
    try:
        response = await commit_auction_lot_grid_edits(
            session,
            payload,
            workspace_id=workspace_id or DEFAULT_GRID_WORKSPACE_ID,
            user_id=current_user.id,
            session_id=grid_session_id,
        )
        await session.rollback()
        return response
    except AuctionGridEditConflictError as error:
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
    except TimeoutError as error:
        await session.rollback()
        raise HTTPException(status_code=504, detail="Grid mutation timed out") from error
    except Exception:
        await session.rollback()
        raise


@router.post("/fill/commit")
async def commit_auction_lots_fill(
    payload: AuctionLotsGridFillRequest | AuctionLotsGridFillCommitRequest,
    workspace_id: str | None = Header(default=None, alias="X-Workspace-Id"),
    grid_session_id: str | None = Header(default=None, alias="X-Grid-Session-Id"),
    session: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> dict[str, object]:
    try:
        if isinstance(payload, AuctionLotsGridFillCommitRequest):
            response = await commit_auction_lot_grid_fill_commit(
                session,
                payload,
                workspace_id=workspace_id or payload.workspace_id or DEFAULT_GRID_WORKSPACE_ID,
                user_id=_resolve_grid_user_id(payload.user_id, current_user),
                session_id=grid_session_id or payload.session_id,
            )
            operation_id = payload.operation_id
            affected_cell_count = len(response.updated_rows) * max(1, len(payload.fill_columns))
        else:
            response = await commit_auction_lot_grid_fill(
                session,
                payload,
                workspace_id=workspace_id or DEFAULT_GRID_WORKSPACE_ID,
                user_id=current_user.id,
                session_id=grid_session_id,
            )
            operation_id = None
            affected_cell_count = len(response.updated_rows)
        await session.commit()
        row_ids = [row.id for row in response.updated_rows]
        return {
            "operationId": operation_id,
            "revision": str(response.dataset_version),
            "datasetVersion": response.dataset_version,
            "updatedRows": [row.model_dump(by_alias=True) for row in response.updated_rows],
            "rows": [row.model_dump(by_alias=True) for row in response.updated_rows],
            "affectedRowCount": len(row_ids),
            "affectedCellCount": affected_cell_count,
            "invalidation": {"type": "rows", "rowIds": row_ids, "reason": "fill"},
            "warnings": [],
        }
    except AuctionGridEditConflictError as error:
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
    except TimeoutError as error:
        await session.rollback()
        raise HTTPException(status_code=504, detail="Grid mutation timed out") from error
    except Exception:
        await session.rollback()
        raise


@router.post("/fill-boundary")
async def resolve_auction_lots_fill_boundary(
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
async def undo_auction_lot_grid_operation(
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
            table_id="auction-lots",
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
    except TimeoutError as error:
        await session.rollback()
        raise HTTPException(status_code=504, detail="Grid mutation timed out") from error
    except Exception:
        await session.rollback()
        raise


@router.post("/operations/{operation_id}/redo")
async def redo_auction_lot_grid_operation(
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
            table_id="auction-lots",
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
    except TimeoutError as error:
        await session.rollback()
        raise HTTPException(status_code=504, detail="Grid mutation timed out") from error
    except Exception:
        await session.rollback()
        raise
