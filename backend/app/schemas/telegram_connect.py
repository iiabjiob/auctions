from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class TelegramConnectTokenResponse(BaseModel):
    connect_url: str
    expires_at: datetime


class TelegramWebhookResult(BaseModel):
    ok: bool = True
    action: str
