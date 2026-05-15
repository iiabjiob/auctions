from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.services.telegram_webhook import TelegramWebhookService


class FakeConnectService:
    def __init__(self, record: object | None) -> None:
        self.record = record
        self.tokens: list[str] = []

    async def consume_connect_token(self, session: object, token: str) -> object | None:
        self.tokens.append(token)
        return self.record


class FakeBindingService:
    def __init__(self, binding: object | None = None) -> None:
        self.binding = binding
        self.chat_ids: list[str] = []
        self.calls: list[tuple[str, str, str | None]] = []

    async def upsert_for_user_id(self, session: object, user_id: str, payload) -> object:  # noqa: ANN001
        self.calls.append((user_id, payload.telegram_chat_id, payload.username))
        return SimpleNamespace(user_id=user_id, telegram_chat_id=payload.telegram_chat_id, username=payload.username)

    async def get_model_for_chat_id(self, session: object, telegram_chat_id: str) -> object | None:
        self.chat_ids.append(telegram_chat_id)
        return self.binding


class FakeSender:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.messages: list[tuple[str, str, str]] = []

    async def send_message(self, *, bot_token: str, chat_id: str, text: str, parse_mode: str) -> None:
        if self.error is not None:
            raise self.error
        self.messages.append((bot_token, chat_id, text))


class FakeScalarResult:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows

    def all(self) -> list[object]:
        return self.rows


class FakeSession:
    def __init__(self, profiles: list[object] | None = None) -> None:
        self.profiles = profiles or []
        self.scalar_statements: list[object] = []

    async def scalars(self, statement: object) -> FakeScalarResult:
        self.scalar_statements.append(statement)
        return FakeScalarResult(self.profiles)


class TelegramWebhookServiceTests(unittest.IsolatedAsyncioTestCase):
    def _reply_text(self, result) -> str:  # noqa: ANN001
        self.assertIsNotNone(result.response_payload)
        self.assertEqual(result.response_payload["method"], "sendMessage")
        self.assertEqual(result.response_payload["parse_mode"], "MarkdownV2")
        return result.response_payload["text"]

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
        self.assertEqual(result.response_payload["chat_id"], "123456")
        text = self._reply_text(result)
        self.assertIn("/status", text)
        self.assertIn("по выбранным срезам", text)

    async def test_handle_update_replies_with_help_for_plain_start(self) -> None:
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
            {"message": {"text": "/start", "chat": {"id": 123456}}},
            bot_token="bot-token",
        )

        self.assertEqual(result.action, "help")
        self.assertEqual(connect_service.tokens, [])
        self.assertEqual(binding_service.calls, [])
        text = self._reply_text(result)
        self.assertIn("кнопку подключения Telegram", text)
        self.assertIn("активные срезы", text)

    async def test_handle_update_replies_with_status_profiles(self) -> None:
        connect_service = FakeConnectService(SimpleNamespace(user_id="user-1"))
        binding_service = FakeBindingService(SimpleNamespace(user_id="user-1"))
        sender = FakeSender()
        service = TelegramWebhookService(
            connect_service=connect_service,
            binding_service=binding_service,
            sender=sender,
        )

        result = await service.handle_update(
            FakeSession([SimpleNamespace(name="BMW <x5>"), SimpleNamespace(name="Коммерческая техника")]),
            {"message": {"text": "/status", "chat": {"id": 123456}}},
            bot_token="bot-token",
        )

        self.assertEqual(result.action, "status")
        self.assertEqual(connect_service.tokens, [])
        self.assertEqual(binding_service.chat_ids, ["123456"])
        text = self._reply_text(result)
        self.assertIn("Активные срезы", text)
        self.assertIn("\\- BMW <x5\\>", text)
        self.assertNotIn("Канал", text)

    async def test_handle_update_replies_with_status_when_chat_is_not_connected(self) -> None:
        connect_service = FakeConnectService(SimpleNamespace(user_id="user-1"))
        binding_service = FakeBindingService(None)
        sender = FakeSender()
        service = TelegramWebhookService(
            connect_service=connect_service,
            binding_service=binding_service,
            sender=sender,
        )

        result = await service.handle_update(
            FakeSession(),
            {"message": {"text": "/status@auction_bot", "chat": {"id": 123456}}},
            bot_token="bot-token",
        )

        self.assertEqual(result.action, "status")
        self.assertEqual(binding_service.chat_ids, ["123456"])
        self.assertIn("пока не подключен", self._reply_text(result))

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

    async def test_handle_update_returns_invalid_token_reply_payload(self) -> None:
        connect_service = FakeConnectService(None)
        binding_service = FakeBindingService()
        service = TelegramWebhookService(connect_service=connect_service, binding_service=binding_service)

        result = await service.handle_update(
            object(),
            {"message": {"text": "/start connect_bad", "chat": {"id": 1}}},
            bot_token="bot-token",
        )

        self.assertEqual(result.action, "invalid_token")
        self.assertIn("Токен подключения не найден", self._reply_text(result))

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
