from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FilterPresetModel, UserModel
from app.schemas.filter_presets import FilterPresetCreate, FilterPresetResponse, FilterPresetUpdate, PresetScope


class FilterPresetService:
    async def list_for_user(self, session: AsyncSession, user: UserModel, scope: PresetScope) -> list[FilterPresetResponse]:
        normalized_scope = self._normalize_scope(scope)
        statement = (
            select(FilterPresetModel)
            .where(FilterPresetModel.owner_user_id == user.id, FilterPresetModel.scope == normalized_scope)
            .order_by(FilterPresetModel.is_favorite.desc(), FilterPresetModel.name.asc())
        )
        presets = (await session.scalars(statement)).all()
        return [FilterPresetResponse.model_validate(preset, from_attributes=True) for preset in presets]

    async def create(
        self,
        session: AsyncSession,
        user: UserModel,
        payload: FilterPresetCreate,
        scope: PresetScope,
    ) -> FilterPresetResponse:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Preset name is required.")
        normalized_scope = self._normalize_scope(scope)
        await self._ensure_name_available(session, user.id, normalized_scope, name)
        preset = FilterPresetModel(
            id=f"preset_{uuid4().hex[:24]}",
            owner_user_id=user.id,
            scope=normalized_scope,
            name=name,
            filters=payload.filters,
            grid_view=payload.grid_view,
            is_favorite=payload.is_favorite,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        session.add(preset)
        await session.commit()
        await session.refresh(preset)
        return FilterPresetResponse.model_validate(preset, from_attributes=True)

    async def update(
        self,
        session: AsyncSession,
        user: UserModel,
        preset_id: str,
        payload: FilterPresetUpdate,
        scope: PresetScope,
    ) -> FilterPresetResponse:
        normalized_scope = self._normalize_scope(scope)
        preset = await self._get_owned_preset(session, user.id, preset_id, normalized_scope)
        updates = payload.model_dump(exclude_unset=True)

        if "name" in updates:
            next_name = str(updates["name"]).strip()
            if not next_name:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Preset name is required.")
            if next_name != preset.name:
                await self._ensure_name_available(session, user.id, normalized_scope, next_name, exclude_id=preset.id)
                preset.name = next_name

        if "filters" in updates:
            preset.filters = updates["filters"]
        if "grid_view" in updates:
            preset.grid_view = updates["grid_view"]
        if "is_favorite" in updates:
            preset.is_favorite = bool(updates["is_favorite"])

        preset.updated_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(preset)
        return FilterPresetResponse.model_validate(preset, from_attributes=True)

    async def delete(self, session: AsyncSession, user: UserModel, preset_id: str, scope: PresetScope) -> None:
        preset = await self._get_owned_preset(session, user.id, preset_id, self._normalize_scope(scope))
        await session.delete(preset)
        await session.commit()

    async def _get_owned_preset(
        self,
        session: AsyncSession,
        user_id: str,
        preset_id: str,
        scope: PresetScope,
    ) -> FilterPresetModel:
        statement = select(FilterPresetModel).where(
            FilterPresetModel.id == preset_id,
            FilterPresetModel.owner_user_id == user_id,
            FilterPresetModel.scope == scope,
        )
        preset = await session.scalar(statement)
        if preset is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Preset not found.")
        return preset

    async def _ensure_name_available(
        self,
        session: AsyncSession,
        user_id: str,
        scope: PresetScope,
        name: str,
        *,
        exclude_id: str | None = None,
    ) -> None:
        statement = select(FilterPresetModel).where(
            FilterPresetModel.owner_user_id == user_id,
            FilterPresetModel.scope == scope,
            FilterPresetModel.name == name,
        )
        existing = await session.scalar(statement)
        if existing is None:
            return
        if exclude_id and existing.id == exclude_id:
            return
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Preset with this name already exists.")

    def _normalize_scope(self, scope: PresetScope) -> PresetScope:
        normalized = scope.strip().lower()
        if normalized not in {"auction", "procurement"}:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid preset scope.")
        return normalized  # type: ignore[return-value]


filter_preset_service = FilterPresetService()
