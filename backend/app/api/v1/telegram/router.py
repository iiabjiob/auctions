from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.infrastructure.db.database import get_db
from app.models import UserModel
from app.schemas.telegram_bindings import TelegramBindingResponse, TelegramBindingUpsert
from app.services.telegram_bindings import telegram_binding_service

router = APIRouter(prefix="/api/v1/telegram", tags=["Telegram"])


@router.get("/binding", response_model=TelegramBindingResponse | None)
async def get_telegram_binding(
    session: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> TelegramBindingResponse | None:
    return await telegram_binding_service.get_for_user(session, current_user)


@router.put("/binding", response_model=TelegramBindingResponse)
async def upsert_telegram_binding(
    payload: TelegramBindingUpsert,
    session: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> TelegramBindingResponse:
    return await telegram_binding_service.upsert_for_user(session, current_user, payload)


@router.delete("/binding", status_code=status.HTTP_204_NO_CONTENT)
async def delete_telegram_binding(
    session: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> Response:
    await telegram_binding_service.delete_for_user(session, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
