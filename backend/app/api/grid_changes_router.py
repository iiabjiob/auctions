from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.infrastructure.db.database import get_read_db
from app.models import UserModel
from app.schemas.grid_changes import GridChangeFeedResponse
from app.services.auction_grid_state import DEFAULT_GRID_WORKSPACE_ID
from app.services.grid_changes import get_grid_changes


router = APIRouter(prefix="/api", tags=["Grid Changes"])


@router.get("/changes", response_model=GridChangeFeedResponse)
async def get_changes(
    table_id: str | None = Query(default=None, alias="tableId", min_length=1),
    since_version: int = Query(default=0, alias="sinceVersion", ge=0),
    limit: int | None = Query(default=None, ge=1),
    workspace_id: str | None = Header(default=None, alias="X-Workspace-Id"),
    grid_table_id: str | None = Header(default=None, alias="X-Grid-Table-Id"),
    session: AsyncSession = Depends(get_read_db),
    current_user: UserModel = Depends(get_current_user),
) -> GridChangeFeedResponse:
    del current_user
    resolved_table_id = table_id or grid_table_id
    if resolved_table_id is None or not resolved_table_id.strip():
        raise HTTPException(status_code=400, detail="tableId or X-Grid-Table-Id is required")
    try:
        return await get_grid_changes(
            session,
            table_id=resolved_table_id,
            since_version=since_version,
            workspace_id=workspace_id or DEFAULT_GRID_WORKSPACE_ID,
            limit=limit,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
