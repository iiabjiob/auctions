from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.infrastructure.db.database import get_db
from app.models import UserModel
from app.schemas.user_interest_profiles import (
    UserInterestProfileCreate,
    UserInterestProfileFromPreset,
    UserInterestProfileResponse,
    UserInterestProfileUpdate,
)
from app.services.user_interest_profiles import user_interest_profile_service

router = APIRouter(prefix="/api/v1/user-interest-profiles", tags=["User Interest Profiles"])


@router.get("", response_model=list[UserInterestProfileResponse])
async def list_user_interest_profiles(
    session: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> list[UserInterestProfileResponse]:
    return await user_interest_profile_service.list_for_user(session, current_user)


@router.post("", response_model=UserInterestProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_user_interest_profile(
    payload: UserInterestProfileCreate,
    session: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> UserInterestProfileResponse:
    return await user_interest_profile_service.create(session, current_user, payload)


@router.post("/from-preset", response_model=UserInterestProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_user_interest_profile_from_preset(
    payload: UserInterestProfileFromPreset,
    session: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> UserInterestProfileResponse:
    return await user_interest_profile_service.create_from_preset(session, current_user, payload)


@router.patch("/{profile_id}", response_model=UserInterestProfileResponse)
async def update_user_interest_profile(
    profile_id: str,
    payload: UserInterestProfileUpdate,
    session: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> UserInterestProfileResponse:
    return await user_interest_profile_service.update(session, current_user, profile_id, payload)


@router.post("/{profile_id}/refresh-from-preset", response_model=UserInterestProfileResponse)
async def refresh_user_interest_profile_from_preset(
    profile_id: str,
    session: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> UserInterestProfileResponse:
    return await user_interest_profile_service.refresh_from_preset(session, current_user, profile_id)


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_interest_profile(
    profile_id: str,
    session: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> Response:
    await user_interest_profile_service.delete(session, current_user, profile_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
