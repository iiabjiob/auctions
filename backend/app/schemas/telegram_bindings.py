from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class TelegramBindingUpsert(BaseModel):
    telegram_chat_id: str = Field(min_length=1, max_length=128)
    username: str | None = Field(default=None, max_length=255)

    @field_validator("telegram_chat_id")
    @classmethod
    def validate_chat_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("telegram_chat_id is required")
        return normalized

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lstrip("@")
        return normalized or None


class TelegramBindingResponse(BaseModel):
    user_id: str
    telegram_chat_id: str
    username: str | None = None
    connected_at: datetime | None = None
    updated_at: datetime | None = None
