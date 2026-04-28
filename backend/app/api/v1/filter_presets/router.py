from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.infrastructure.db.database import get_db
from app.models import UserModel
from app.schemas.filter_presets import FilterPresetCreate, FilterPresetResponse, FilterPresetUpdate
from app.services.filter_presets import filter_preset_service

router = APIRouter(prefix="/api/v1/filter-presets", tags=["Filter Presets"])


@router.get("", response_model=list[FilterPresetResponse])
async def list_filter_presets(
    session: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> list[FilterPresetResponse]:
    return await filter_preset_service.list_for_user(session, current_user)


@router.post("", response_model=FilterPresetResponse, status_code=status.HTTP_201_CREATED)
async def create_filter_preset(
    payload: FilterPresetCreate,
    session: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> FilterPresetResponse:
    return await filter_preset_service.create(session, current_user, payload)


@router.patch("/{preset_id}", response_model=FilterPresetResponse)
async def update_filter_preset(
    preset_id: str,
    payload: FilterPresetUpdate,
    session: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> FilterPresetResponse:
    return await filter_preset_service.update(session, current_user, preset_id, payload)


@router.delete("/{preset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_filter_preset(
    preset_id: str,
    session: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> Response:
    await filter_preset_service.delete(session, current_user, preset_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
