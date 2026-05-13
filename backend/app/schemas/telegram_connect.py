from __future__ import annotations

from typing import Any

from datetime import datetime

from pydantic import BaseModel


class TelegramConnectTokenResponse(BaseModel):
    connect_url: str
    expires_at: datetime


class TelegramWebhookResult(BaseModel):
    ok: bool = True
    action: str
    response_payload: dict[str, Any] | None = None
