from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UserInterestProfileModel, UserModel
from app.schemas.user_interest_profiles import (
    UserInterestProfileCreate,
    UserInterestProfileResponse,
    UserInterestProfileUpdate,
)


class UserInterestProfileService:
    async def list_for_user(self, session: AsyncSession, user: UserModel) -> list[UserInterestProfileResponse]:
        statement = (
            select(UserInterestProfileModel)
            .where(UserInterestProfileModel.owner_user_id == user.id)
            .order_by(UserInterestProfileModel.is_active.desc(), UserInterestProfileModel.name.asc())
        )
        profiles = (await session.scalars(statement)).all()
        return [UserInterestProfileResponse.model_validate(profile, from_attributes=True) for profile in profiles]

    async def create(
        self,
        session: AsyncSession,
        user: UserModel,
        payload: UserInterestProfileCreate,
    ) -> UserInterestProfileResponse:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Profile name is required.")
        await self._ensure_name_available(session, user.id, name)
        profile = UserInterestProfileModel(
            id=f"uip_{uuid4().hex[:24]}",
            owner_user_id=user.id,
            name=name,
            profile_payload=payload.profile_payload,
            min_rating=payload.min_rating,
            notification_priority_threshold=payload.notification_priority_threshold,
            telegram_enabled=payload.telegram_enabled,
            is_active=payload.is_active,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        session.add(profile)
        await session.commit()
        await session.refresh(profile)
        return UserInterestProfileResponse.model_validate(profile, from_attributes=True)

    async def update(
        self,
        session: AsyncSession,
        user: UserModel,
        profile_id: str,
        payload: UserInterestProfileUpdate,
    ) -> UserInterestProfileResponse:
        profile = await self._get_owned_profile(session, user.id, profile_id)
        updates = payload.model_dump(exclude_unset=True)

        if "name" in updates:
            next_name = str(updates["name"]).strip()
            if not next_name:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Profile name is required.",
                )
            if next_name != profile.name:
                await self._ensure_name_available(session, user.id, next_name, exclude_id=profile.id)
                profile.name = next_name

        if "profile_payload" in updates:
            profile.profile_payload = updates["profile_payload"]
        if "min_rating" in updates:
            profile.min_rating = updates["min_rating"]
        if "notification_priority_threshold" in updates:
            profile.notification_priority_threshold = updates["notification_priority_threshold"]
        if "telegram_enabled" in updates:
            profile.telegram_enabled = bool(updates["telegram_enabled"])
        if "is_active" in updates:
            profile.is_active = bool(updates["is_active"])

        profile.updated_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(profile)
        return UserInterestProfileResponse.model_validate(profile, from_attributes=True)

    async def delete(self, session: AsyncSession, user: UserModel, profile_id: str) -> None:
        profile = await self._get_owned_profile(session, user.id, profile_id)
        await session.delete(profile)
        await session.commit()

    async def _get_owned_profile(
        self,
        session: AsyncSession,
        user_id: str,
        profile_id: str,
    ) -> UserInterestProfileModel:
        statement = select(UserInterestProfileModel).where(
            UserInterestProfileModel.id == profile_id,
            UserInterestProfileModel.owner_user_id == user_id,
        )
        profile = await session.scalar(statement)
        if profile is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found.")
        return profile

    async def _ensure_name_available(
        self,
        session: AsyncSession,
        user_id: str,
        name: str,
        *,
        exclude_id: str | None = None,
    ) -> None:
        statement = select(UserInterestProfileModel).where(
            UserInterestProfileModel.owner_user_id == user_id,
            UserInterestProfileModel.name == name,
        )
        existing = await session.scalar(statement)
        if existing is None:
            return
        if exclude_id and existing.id == exclude_id:
            return
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Profile with this name already exists.")


user_interest_profile_service = UserInterestProfileService()
