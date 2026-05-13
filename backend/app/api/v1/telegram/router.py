from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import Settings, get_settings
from app.infrastructure.db.database import get_db
from app.models import UserModel
from app.schemas.telegram_connect import TelegramConnectTokenResponse, TelegramWebhookResult
from app.schemas.telegram_bindings import TelegramBindingResponse, TelegramBindingUpsert
from app.services.telegram_bindings import telegram_binding_service
from app.services.telegram_connect import TelegramConnectError, telegram_connect_service
from app.services.telegram_webhook import telegram_webhook_service

router = APIRouter(prefix="/api/v1/telegram", tags=["Telegram"])


@router.get("/binding", response_model=TelegramBindingResponse | None)
async def get_telegram_binding(
    session: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> TelegramBindingResponse | None:
    return await telegram_binding_service.get_for_user(session, current_user)


@router.post("/connect-token", response_model=TelegramConnectTokenResponse)
async def create_telegram_connect_token(
    session: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> TelegramConnectTokenResponse:
    try:
        return await telegram_connect_service.create_connect_token(
            session,
            current_user,
            bot_username=settings.telegram_bot_username,
            ttl_seconds=settings.telegram_connect_token_ttl_seconds,
        )
    except TelegramConnectError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


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


@router.post("/webhook", include_in_schema=False)
async def handle_telegram_webhook(
    update: dict[str, Any],
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any] | TelegramWebhookResult:
    if settings.telegram_webhook_secret is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="telegram_webhook_secret is not configured")
    if x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Telegram webhook secret")
    result = await telegram_webhook_service.handle_update(
        session,
        update,
        bot_token=settings.telegram_bot_token,
        channel_url=settings.telegram_channel_url,
    )
    if result.response_payload is not None:
        return result.response_payload
    return result
