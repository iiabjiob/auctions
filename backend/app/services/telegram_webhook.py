from __future__ import annotations

from html import escape
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UserInterestProfileModel
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
            if not self._is_start_command(text) and not self._is_status_command(text):
                return TelegramWebhookResult(action="ignored")

            chat_id = self._message_chat_id(message)
            if chat_id is None:
                return TelegramWebhookResult(action="invalid_chat")

            if self._is_start_command(text):
                await self._send_reply(bot_token=bot_token, chat_id=chat_id, text=self._help_message())
                return TelegramWebhookResult(action="help")

            await self._send_status_reply(session, bot_token=bot_token, chat_id=chat_id)
            return TelegramWebhookResult(action="status")

        chat_id = self._message_chat_id(message)
        if chat_id is None:
            return TelegramWebhookResult(action="invalid_chat")

        record = await self._connect_service.consume_connect_token(session, token)
        if record is None:
            await self._send_reply(
                bot_token=bot_token,
                chat_id=chat_id,
                text="Токен подключения не найден, уже использован или истек. Создайте новую ссылку в приложении.",
            )
            return TelegramWebhookResult(action="invalid_token")

        sender = message.get("from")
        username = sender.get("username") if isinstance(sender, dict) else None
        payload = TelegramBindingUpsert(telegram_chat_id=chat_id, username=username)
        await self._binding_service.upsert_for_user_id(session, record.user_id, payload)
        await self._send_reply(
            bot_token=bot_token,
            chat_id=chat_id,
            text=(
                "Telegram подключен. Теперь уведомления будут приходить по выбранным профилям интересов.\n\n"
                "Команда /status покажет активные подборки."
            ),
        )
        return TelegramWebhookResult(action="connected")

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
        return (
            "Чтобы подключить уведомления, откройте приложение и нажмите кнопку подключения Telegram.\n\n"
            "После подключения используйте /status, чтобы увидеть активные подборки."
        )

    async def _send_status_reply(self, session: AsyncSession, *, bot_token: str | None, chat_id: str) -> None:
        binding = await self._binding_service.get_model_for_chat_id(session, chat_id)
        if binding is None:
            await self._send_reply(
                bot_token=bot_token,
                chat_id=chat_id,
                text=(
                    "Telegram пока не подключен к аккаунту.\n\n"
                    "Откройте приложение и нажмите кнопку подключения Telegram."
                ),
            )
            return

        profiles = await self._active_telegram_profiles(session, binding.user_id)
        if not profiles:
            await self._send_reply(
                bot_token=bot_token,
                chat_id=chat_id,
                text="Telegram подключен, но активных подборок с уведомлениями пока нет.",
            )
            return

        visible_profiles = profiles[:10]
        lines = ["Telegram подключен. Активные подборки:"]
        lines.extend(f"• {escape(profile.name)}" for profile in visible_profiles)
        if len(profiles) > len(visible_profiles):
            lines.append(f"и еще {len(profiles) - len(visible_profiles)}")
        await self._send_reply(bot_token=bot_token, chat_id=chat_id, text="\n".join(lines))

    async def _active_telegram_profiles(self, session: AsyncSession, user_id: str) -> list[UserInterestProfileModel]:
        statement = (
            select(UserInterestProfileModel)
            .where(UserInterestProfileModel.owner_user_id == user_id)
            .where(UserInterestProfileModel.is_active.is_(True))
            .where(UserInterestProfileModel.telegram_enabled.is_(True))
            .order_by(UserInterestProfileModel.name.asc(), UserInterestProfileModel.id.asc())
        )
        return list((await session.scalars(statement)).all())

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
