from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.telegram_bindings import TelegramBindingUpsert
from app.schemas.telegram_connect import TelegramWebhookResult
from app.services.telegram_bindings import TelegramBindingService, telegram_binding_service
from app.services.telegram_connect import TELEGRAM_START_PREFIX, TelegramConnectService, telegram_connect_service
from app.services.telegram_sender import TelegramBotApiSender, TelegramMessageSender, TelegramSenderError


class TelegramWebhookService:
    def __init__(
        self,
        *,
        connect_service: TelegramConnectService = telegram_connect_service,
        binding_service: TelegramBindingService = telegram_binding_service,
        sender: TelegramMessageSender | None = None,
    ) -> None:
        self._connect_service = connect_service
        self._binding_service = binding_service
        self._sender = sender or TelegramBotApiSender()

    async def handle_update(
        self,
        session: AsyncSession,
        update: dict[str, Any],
        *,
        bot_token: str | None = None,
    ) -> TelegramWebhookResult:
        message = update.get("message")
        if not isinstance(message, dict):
            return TelegramWebhookResult(action="ignored")

        text = message.get("text")
        if not isinstance(text, str):
            return TelegramWebhookResult(action="ignored")

        token = self._extract_connect_token(text)
        if token is None:
            return TelegramWebhookResult(action="ignored")

        chat = message.get("chat")
        if not isinstance(chat, dict) or chat.get("id") is None:
            return TelegramWebhookResult(action="invalid_chat")

        record = await self._connect_service.consume_connect_token(session, token)
        if record is None:
            await self._send_reply(
                bot_token=bot_token,
                chat_id=str(chat["id"]),
                text="Токен подключения не найден, уже использован или истек. Создайте новую ссылку в приложении.",
            )
            return TelegramWebhookResult(action="invalid_token")

        sender = message.get("from")
        username = sender.get("username") if isinstance(sender, dict) else None
        payload = TelegramBindingUpsert(telegram_chat_id=str(chat["id"]), username=username)
        await self._binding_service.upsert_for_user_id(session, record.user_id, payload)
        await self._send_reply(
            bot_token=bot_token,
            chat_id=str(chat["id"]),
            text="Telegram подключен. Теперь уведомления будут приходить по выбранным профилям интересов.",
        )
        return TelegramWebhookResult(action="connected")

    def _extract_connect_token(self, text: str) -> str | None:
        parts = text.strip().split(maxsplit=1)
        if len(parts) != 2 or parts[0] != "/start":
            return None
        payload = parts[1].strip()
        if not payload.startswith(TELEGRAM_START_PREFIX):
            return None
        token = payload.removeprefix(TELEGRAM_START_PREFIX).strip()
        return token or None

    async def _send_reply(self, *, bot_token: str | None, chat_id: str, text: str) -> None:
        if not bot_token:
            return
        try:
            await self._sender.send_message(
                bot_token=bot_token,
                chat_id=chat_id,
                text=text,
                parse_mode="HTML",
            )
        except TelegramSenderError:
            return


telegram_webhook_service = TelegramWebhookService()
