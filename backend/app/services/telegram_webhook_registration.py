from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


TELEGRAM_SET_WEBHOOK_URL_TEMPLATE = "https://api.telegram.org/bot{bot_token}/setWebhook"


class TelegramWebhookRegistrationError(Exception):
    pass


@dataclass(frozen=True)
class TelegramWebhookRegistrationResult:
    registered: bool
    reason: str | None = None


class TelegramWebhookRegistrar:
    def __init__(self, *, timeout_seconds: float = 10.0) -> None:
        self.timeout_seconds = timeout_seconds

    async def ensure_webhook(
        self,
        *,
        bot_token: str | None,
        webhook_url: str | None,
        webhook_secret: str | None,
        enabled: bool,
    ) -> TelegramWebhookRegistrationResult:
        if not enabled:
            return TelegramWebhookRegistrationResult(registered=False, reason="disabled")
        if not bot_token:
            return TelegramWebhookRegistrationResult(registered=False, reason="missing_bot_token")
        if not webhook_url:
            return TelegramWebhookRegistrationResult(registered=False, reason="missing_webhook_url")
        if not webhook_secret:
            return TelegramWebhookRegistrationResult(registered=False, reason="missing_webhook_secret")

        await asyncio.to_thread(
            self._set_webhook_sync,
            bot_token=bot_token,
            webhook_url=webhook_url,
            webhook_secret=webhook_secret,
        )
        return TelegramWebhookRegistrationResult(registered=True)

    def _set_webhook_sync(self, *, bot_token: str, webhook_url: str, webhook_secret: str) -> None:
        payload = json.dumps(
            {
                "url": webhook_url,
                "secret_token": webhook_secret,
                "allowed_updates": ["message"],
            }
        ).encode("utf-8")
        request = Request(
            TELEGRAM_SET_WEBHOOK_URL_TEMPLATE.format(bot_token=bot_token),
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            raise TelegramWebhookRegistrationError(_telegram_http_error_message(error)) from error
        except (TimeoutError, URLError, OSError) as error:
            raise TelegramWebhookRegistrationError(str(error) or "Telegram setWebhook request failed") from error
        if not isinstance(response_payload, dict) or not response_payload.get("ok"):
            description = response_payload.get("description") if isinstance(response_payload, dict) else None
            raise TelegramWebhookRegistrationError(description or "Telegram setWebhook returned unsuccessful response")


def _telegram_http_error_message(error: HTTPError) -> str:
    fallback = f"Telegram HTTP {error.code}"
    try:
        payload = error.read().decode("utf-8")
    except Exception:
        return fallback
    if not payload:
        return fallback
    try:
        response = json.loads(payload)
    except json.JSONDecodeError:
        return f"{fallback}: {payload[:500]}"
    if isinstance(response, dict):
        description = response.get("description")
        if description:
            return f"{fallback}: {description}"
    return f"{fallback}: {payload[:500]}"


telegram_webhook_registrar = TelegramWebhookRegistrar()
