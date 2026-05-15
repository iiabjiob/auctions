from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UserInterestProfileModel
from app.schemas.telegram_bindings import TelegramBindingUpsert
from app.schemas.telegram_connect import TelegramWebhookResult
from app.services.telegram_bindings import TelegramBindingService, telegram_binding_service
from app.services.telegram_connect import TELEGRAM_START_PREFIX, TelegramConnectService, telegram_connect_service
from app.services.telegram_sender import TelegramBotApiSender, TelegramMessageSender


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
            if not self._is_start_command(text) and not self._is_status_command(text):
                return TelegramWebhookResult(action="ignored")

            chat_id = self._message_chat_id(message)
            if chat_id is None:
                return TelegramWebhookResult(action="invalid_chat")

            if self._is_start_command(text):
                return self._reply_result(action="help", chat_id=chat_id, text=self._help_message())

            return await self._status_reply_result(session, chat_id=chat_id)

        chat_id = self._message_chat_id(message)
        if chat_id is None:
            return TelegramWebhookResult(action="invalid_chat")

        record = await self._connect_service.consume_connect_token(session, token)
        if record is None:
            return self._reply_result(
                action="invalid_token",
                chat_id=chat_id,
                text=_markdown_v2(
                    "Токен подключения не найден, уже использован или истек. Создайте новую ссылку в приложении."
                ),
            )

        sender = message.get("from")
        username = sender.get("username") if isinstance(sender, dict) else None
        payload = TelegramBindingUpsert(telegram_chat_id=chat_id, username=username)
        await self._binding_service.upsert_for_user_id(session, record.user_id, payload)
        return self._reply_result(
            action="connected",
            chat_id=chat_id,
            text=self._connected_message(),
        )

    def _is_start_command(self, text: str) -> bool:
        return self._command_name(text) == "/start"

    def _is_status_command(self, text: str) -> bool:
        return self._command_name(text) == "/status"

    def _command_name(self, text: str) -> str:
        parts = text.strip().split(maxsplit=1)
        if not parts:
            return ""
        command = parts[0].split("@", 1)[0]
        return command.lower()

    def _message_chat_id(self, message: dict[str, Any]) -> str | None:
        chat = message.get("chat")
        if not isinstance(chat, dict) or chat.get("id") is None:
            return None
        return str(chat["id"])

    def _extract_connect_token(self, text: str) -> str | None:
        parts = text.strip().split(maxsplit=1)
        if len(parts) != 2 or self._command_name(parts[0]) != "/start":
            return None
        payload = parts[1].strip()
        if not payload.startswith(TELEGRAM_START_PREFIX):
            return None
        token = payload.removeprefix(TELEGRAM_START_PREFIX).strip()
        return token or None

    def _help_message(self) -> str:
        return "\n\n".join(
            [
                _markdown_v2("Чтобы подключить уведомления, откройте приложение и нажмите кнопку подключения Telegram."),
                _markdown_v2("После подключения используйте /status, чтобы увидеть активные срезы."),
            ]
        )

    def _connected_message(self) -> str:
        return "\n\n".join(
            [
                _markdown_v2("Telegram подключен. Теперь уведомления будут приходить по выбранным срезам."),
                _markdown_v2("Команда /status покажет активные срезы."),
            ]
        )

    async def _status_reply_result(
        self,
        session: AsyncSession,
        *,
        chat_id: str,
    ) -> TelegramWebhookResult:
        binding = await self._binding_service.get_model_for_chat_id(session, chat_id)
        if binding is None:
            return self._reply_result(
                action="status",
                chat_id=chat_id,
                text="\n\n".join(
                    [
                        _markdown_v2("Telegram пока не подключен к аккаунту."),
                        _markdown_v2("Откройте приложение и нажмите кнопку подключения Telegram."),
                    ]
                ),
            )

        profiles = await self._active_telegram_profiles(session, binding.user_id)
        if not profiles:
            message = _markdown_v2("Telegram подключен, но активных подборок с уведомлениями пока нет.")
            return self._reply_result(action="status", chat_id=chat_id, text=message)

        visible_profiles = profiles[:10]
        lines = [_markdown_v2("Telegram подключен. Активные срезы:")]
        lines.extend(f"\\- {_markdown_v2(profile.name)}" for profile in visible_profiles)
        if len(profiles) > len(visible_profiles):
            lines.append(_markdown_v2(f"и еще {len(profiles) - len(visible_profiles)}"))
        return self._reply_result(action="status", chat_id=chat_id, text="\n".join(lines))

    async def _active_telegram_profiles(self, session: AsyncSession, user_id: str) -> list[UserInterestProfileModel]:
        statement = (
            select(UserInterestProfileModel)
            .where(UserInterestProfileModel.owner_user_id == user_id)
            .where(UserInterestProfileModel.is_active.is_(True))
            .where(UserInterestProfileModel.telegram_enabled.is_(True))
            .order_by(UserInterestProfileModel.name.asc(), UserInterestProfileModel.id.asc())
        )
        return list((await session.scalars(statement)).all())

    def _reply_result(self, *, action: str, chat_id: str, text: str) -> TelegramWebhookResult:
        return TelegramWebhookResult(
            action=action,
            response_payload={
                "method": "sendMessage",
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "MarkdownV2",
                "disable_web_page_preview": True,
            },
        )


def _markdown_v2(value: object) -> str:
    return re.sub(r"([_*\[\]()~`>#+\-=|{}.!\\])", r"\\\1", str(value))


telegram_webhook_service = TelegramWebhookService()
