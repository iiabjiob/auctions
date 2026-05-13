from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FilterPresetModel, UserInterestProfileModel, UserModel
from app.schemas.user_interest_profiles import (
    UserInterestProfileCreate,
    UserInterestProfileFromPreset,
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
            source_filter_preset_id=payload.source_filter_preset_id,
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

    async def create_from_preset(
        self,
        session: AsyncSession,
        user: UserModel,
        payload: UserInterestProfileFromPreset,
    ) -> UserInterestProfileResponse:
        preset = await self._get_owned_preset(session, user.id, payload.preset_id)
        name = (payload.name or preset.name).strip()
        if not name:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Profile name is required.")
        await self._ensure_name_available(session, user.id, name)
        profile_payload = build_profile_payload_from_filter_preset(preset.filters)
        min_rating = payload.min_rating
        if min_rating is None:
            min_rating = _filter_int(preset.filters, "minRating", "min_rating") or 0
        profile = UserInterestProfileModel(
            id=f"uip_{uuid4().hex[:24]}",
            owner_user_id=user.id,
            source_filter_preset_id=preset.id,
            name=name,
            profile_payload=profile_payload,
            min_rating=min_rating,
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
        if "source_filter_preset_id" in updates:
            profile.source_filter_preset_id = updates["source_filter_preset_id"]
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

    async def refresh_from_preset(
        self,
        session: AsyncSession,
        user: UserModel,
        profile_id: str,
    ) -> UserInterestProfileResponse:
        profile = await self._get_owned_profile(session, user.id, profile_id)
        if not profile.source_filter_preset_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Profile is not linked to a preset.")
        preset = await self._get_owned_preset(session, user.id, profile.source_filter_preset_id)
        profile.profile_payload = build_profile_payload_from_filter_preset(preset.filters)
        preset_min_rating = _filter_int(preset.filters, "minRating", "min_rating")
        if preset_min_rating is not None:
            profile.min_rating = preset_min_rating
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

    async def _get_owned_preset(self, session: AsyncSession, user_id: str, preset_id: str) -> FilterPresetModel:
        statement = select(FilterPresetModel).where(
            FilterPresetModel.id == preset_id,
            FilterPresetModel.owner_user_id == user_id,
        )
        preset = await session.scalar(statement)
        if preset is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Preset not found.")
        return preset


def build_profile_payload_from_filter_preset(filters: dict) -> dict:
    payload = {
        "profile_identifier": None,
        "target_regions": _filter_text_list(filters, "targetRegions", "target_regions", "regions"),
        "target_categories": _filter_text_list(
            filters,
            "targetCategories",
            "target_categories",
            "categories",
            "analysisCategory",
            "category",
        ),
        "budget_min": _filter_number(filters, "minPrice", "min_price", "budget_min"),
        "budget_max": _filter_number(filters, "maxPrice", "max_price", "budget_max"),
        "minimum_roi": None,
        "minimum_discount": None,
        "allowed_legal_risks": _filter_text_list(filters, "allowedLegalRisks", "allowed_legal_risks")
        or ["low", "medium"],
        "max_distance_km": None,
        "stop_words": _filter_text_list(filters, "stopWords", "stop_words"),
        "desired_keywords": _filter_text_list(filters, "desiredKeywords", "desired_keywords", "q", "status"),
        "strategy": "balanced",
        "weights": {},
    }
    return {key: value for key, value in payload.items() if value not in (None, [], {})}


def _filter_text_list(filters: dict, *keys: str) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for key in keys:
        value = filters.get(key)
        candidates = value if isinstance(value, list) else str(value or "").split(",")
        for candidate in candidates:
            text = str(candidate or "").strip()
            normalized = text.casefold()
            if not text or normalized in seen or normalized == "all":
                continue
            seen.add(normalized)
            values.append(text)
    return values


def _filter_number(filters: dict, *keys: str) -> str | None:
    for key in keys:
        value = filters.get(key)
        if value is None:
            continue
        normalized = str(value).strip().replace(" ", "").replace(",", ".")
        if not normalized:
            continue
        try:
            number = float(normalized)
        except ValueError:
            continue
        if number.is_integer():
            return str(int(number))
        return str(number)
    return None


def _filter_int(filters: dict, *keys: str) -> int | None:
    value = _filter_number(filters, *keys)
    if value is None:
        return None
    return max(0, min(100, int(float(value))))


user_interest_profile_service = UserInterestProfileService()
