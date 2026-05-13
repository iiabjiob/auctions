from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UserModel, UserTelegramBindingModel
from app.schemas.telegram_bindings import TelegramBindingResponse, TelegramBindingUpsert


class TelegramBindingService:
    async def get_for_user(
        self,
        session: AsyncSession,
        user: UserModel,
    ) -> TelegramBindingResponse | None:
        binding = await self._get_model_for_user(session, user.id)
        if binding is None:
            return None
        return TelegramBindingResponse.model_validate(binding, from_attributes=True)

    async def upsert_for_user(
        self,
        session: AsyncSession,
        user: UserModel,
        payload: TelegramBindingUpsert,
    ) -> TelegramBindingResponse:
        binding = await self._get_model_for_user(session, user.id)
        current_time = datetime.now(UTC)
        if binding is None:
            binding = UserTelegramBindingModel(
                user_id=user.id,
                telegram_chat_id=payload.telegram_chat_id,
                username=payload.username,
                connected_at=current_time,
                updated_at=current_time,
            )
            session.add(binding)
        else:
            binding.telegram_chat_id = payload.telegram_chat_id
            binding.username = payload.username
            binding.updated_at = current_time

        await session.commit()
        await session.refresh(binding)
        return TelegramBindingResponse.model_validate(binding, from_attributes=True)

    async def delete_for_user(self, session: AsyncSession, user: UserModel) -> None:
        binding = await self._get_model_for_user(session, user.id)
        if binding is None:
            return
        await session.delete(binding)
        await session.commit()

    async def _get_model_for_user(
        self,
        session: AsyncSession,
        user_id: str,
    ) -> UserTelegramBindingModel | None:
        statement = select(UserTelegramBindingModel).where(UserTelegramBindingModel.user_id == user_id)
        return await session.scalar(statement)


telegram_binding_service = TelegramBindingService()
