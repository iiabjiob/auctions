from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ScoringProfileModel
from app.schemas.scoring_profile import LotScoringProfile, build_lot_scoring_profile_hash


class ScoringProfileStoreService:
    def normalize_profile_payload(self, payload: dict[str, Any] | LotScoringProfile) -> LotScoringProfile:
        if isinstance(payload, LotScoringProfile):
            return payload
        return LotScoringProfile.model_validate(payload)

    def build_profile_record(
        self,
        name: str,
        payload: dict[str, Any] | LotScoringProfile,
        *,
        is_active: bool = False,
    ) -> ScoringProfileModel:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("Profile name is required.")

        profile = self.normalize_profile_payload(payload)
        resolved_identifier = profile.profile_identifier or normalized_name
        resolved_profile = profile.model_copy(update={"profile_identifier": resolved_identifier})
        profile_hash = build_lot_scoring_profile_hash(resolved_profile)
        return ScoringProfileModel(
            name=normalized_name,
            profile_identifier=resolved_identifier,
            profile_payload=resolved_profile.canonical_payload(),
            profile_hash=profile_hash,
            is_active=is_active,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    async def save_profile(
        self,
        session: AsyncSession,
        name: str,
        payload: dict[str, Any] | LotScoringProfile,
        *,
        is_active: bool = False,
    ) -> ScoringProfileModel:
        profile = self.build_profile_record(name, payload, is_active=is_active)
        session.add(profile)
        await session.commit()
        await session.refresh(profile)
        return profile

    async def get_active_profile(self, session: AsyncSession) -> ScoringProfileModel | None:
        statement = (
            select(ScoringProfileModel)
            .where(ScoringProfileModel.is_active.is_(True))
            .order_by(ScoringProfileModel.updated_at.desc(), ScoringProfileModel.id.desc())
            .limit(1)
        )
        return await session.scalar(statement)

    async def get_active_scoring_profile(
        self,
        session: AsyncSession,
    ) -> tuple[LotScoringProfile | None, str | None]:
        profile = await self.get_active_profile(session)
        if profile is None:
            return None, None
        normalized_profile = LotScoringProfile.model_validate(profile.profile_payload)
        return normalized_profile, profile.profile_hash


scoring_profile_store_service = ScoringProfileStoreService()
