from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import TelegramConnectTokenModel, UserModel
from app.schemas.telegram_connect import TelegramConnectTokenResponse


TELEGRAM_START_PREFIX = "connect_"
TELEGRAM_START_MAX_BYTES = 64


class TelegramConnectError(ValueError):
    pass


def hash_connect_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def build_connect_url(bot_username: str, token: str) -> str:
    username = bot_username.strip().lstrip("@")
    if not username:
        raise TelegramConnectError("telegram_bot_username is not configured")
    start_payload = f"{TELEGRAM_START_PREFIX}{token}"
    if len(start_payload.encode("utf-8")) > TELEGRAM_START_MAX_BYTES:
        raise TelegramConnectError("telegram connect token is too long for Telegram start payload")
    return f"https://t.me/{username}?start={start_payload}"


class TelegramConnectService:
    async def create_connect_token(
        self,
        session: AsyncSession,
        user: UserModel,
        *,
        bot_username: str | None,
        ttl_seconds: int,
    ) -> TelegramConnectTokenResponse:
        if bot_username is None:
            raise TelegramConnectError("telegram_bot_username is not configured")
        ttl = max(60, ttl_seconds)
        token = token_urlsafe(24)
        expires_at = datetime.now(UTC) + timedelta(seconds=ttl)
        record = TelegramConnectTokenModel(
            id=uuid4().hex,
            user_id=user.id,
            token_hash=hash_connect_token(token),
            expires_at=expires_at,
        )
        session.add(record)
        await session.commit()
        return TelegramConnectTokenResponse(
            connect_url=build_connect_url(bot_username, token),
            expires_at=expires_at,
        )

    async def consume_connect_token(
        self,
        session: AsyncSession,
        token: str,
    ) -> TelegramConnectTokenModel | None:
        token_hash = hash_connect_token(token)
        statement = select(TelegramConnectTokenModel).where(TelegramConnectTokenModel.token_hash == token_hash)
        record = await session.scalar(statement)
        now = datetime.now(UTC)
        if record is None or record.used_at is not None or record.expires_at <= now:
            return None
        record.used_at = now
        await session.commit()
        await session.refresh(record)
        return record


telegram_connect_service = TelegramConnectService()
