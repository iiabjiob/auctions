from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.services.telegram_sender import TelegramSenderError
from app.services.telegram_webhook import TelegramWebhookService


class FakeConnectService:
    def __init__(self, record: object | None) -> None:
        self.record = record
        self.tokens: list[str] = []

    async def consume_connect_token(self, session: object, token: str) -> object | None:
        self.tokens.append(token)
        return self.record


class FakeBindingService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str | None]] = []

    async def upsert_for_user_id(self, session: object, user_id: str, payload) -> object:  # noqa: ANN001
        self.calls.append((user_id, payload.telegram_chat_id, payload.username))
        return SimpleNamespace(user_id=user_id, telegram_chat_id=payload.telegram_chat_id, username=payload.username)


class FakeSender:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.messages: list[tuple[str, str, str]] = []

    async def send_message(self, *, bot_token: str, chat_id: str, text: str, parse_mode: str) -> None:
        if self.error is not None:
            raise self.error
        self.messages.append((bot_token, chat_id, text))


class TelegramWebhookServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_handle_update_connects_user_from_start_token(self) -> None:
        connect_service = FakeConnectService(SimpleNamespace(user_id="user-1"))
        binding_service = FakeBindingService()
        service = TelegramWebhookService(connect_service=connect_service, binding_service=binding_service)

        result = await service.handle_update(
            object(),
            {
                "message": {
                    "text": "/start connect_plain-token",
                    "chat": {"id": 123456},
                    "from": {"username": "auction_user"},
                }
            },
        )

        self.assertEqual(result.action, "connected")
        self.assertEqual(connect_service.tokens, ["plain-token"])
        self.assertEqual(binding_service.calls, [("user-1", "123456", "auction_user")])

    async def test_handle_update_sends_success_reply_when_bot_token_is_configured(self) -> None:
        connect_service = FakeConnectService(SimpleNamespace(user_id="user-1"))
        binding_service = FakeBindingService()
        sender = FakeSender()
        service = TelegramWebhookService(
            connect_service=connect_service,
            binding_service=binding_service,
            sender=sender,
        )

        result = await service.handle_update(
            object(),
            {"message": {"text": "/start connect_plain-token", "chat": {"id": 123456}}},
            bot_token="bot-token",
        )

        self.assertEqual(result.action, "connected")
        self.assertEqual(len(sender.messages), 1)
        self.assertEqual(sender.messages[0][0], "bot-token")
        self.assertEqual(sender.messages[0][1], "123456")

    async def test_handle_update_ignores_unrelated_messages(self) -> None:
        connect_service = FakeConnectService(SimpleNamespace(user_id="user-1"))
        binding_service = FakeBindingService()
        service = TelegramWebhookService(connect_service=connect_service, binding_service=binding_service)

        result = await service.handle_update(object(), {"message": {"text": "hello", "chat": {"id": 1}}})

        self.assertEqual(result.action, "ignored")
        self.assertEqual(connect_service.tokens, [])
        self.assertEqual(binding_service.calls, [])

    async def test_handle_update_rejects_invalid_token(self) -> None:
        connect_service = FakeConnectService(None)
        binding_service = FakeBindingService()
        service = TelegramWebhookService(connect_service=connect_service, binding_service=binding_service)

        result = await service.handle_update(
            object(),
            {"message": {"text": "/start connect_bad", "chat": {"id": 1}}},
        )

        self.assertEqual(result.action, "invalid_token")
        self.assertEqual(connect_service.tokens, ["bad"])
        self.assertEqual(binding_service.calls, [])

    async def test_handle_update_does_not_fail_when_reply_fails(self) -> None:
        connect_service = FakeConnectService(None)
        binding_service = FakeBindingService()
        service = TelegramWebhookService(
            connect_service=connect_service,
            binding_service=binding_service,
            sender=FakeSender(TelegramSenderError("telegram unavailable")),
        )

        result = await service.handle_update(
            object(),
            {"message": {"text": "/start connect_bad", "chat": {"id": 1}}},
            bot_token="bot-token",
        )

        self.assertEqual(result.action, "invalid_token")

    async def test_handle_update_requires_chat_id(self) -> None:
        connect_service = FakeConnectService(SimpleNamespace(user_id="user-1"))
        binding_service = FakeBindingService()
        service = TelegramWebhookService(connect_service=connect_service, binding_service=binding_service)

        result = await service.handle_update(object(), {"message": {"text": "/start connect_token"}})

        self.assertEqual(result.action, "invalid_chat")
        self.assertEqual(connect_service.tokens, [])
        self.assertEqual(binding_service.calls, [])


if __name__ == "__main__":
    unittest.main()
