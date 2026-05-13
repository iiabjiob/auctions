from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.models import UserTelegramBindingModel
from app.schemas.telegram_bindings import TelegramBindingUpsert
from app.services.telegram_bindings import TelegramBindingService


class FakeSession:
    def __init__(self, scalar_results: list[object | None] | None = None) -> None:
        self.scalar_results = list(scalar_results or [])
        self.scalar_statements = []
        self.added: list[object] = []
        self.deleted: list[object] = []
        self.commits = 0
        self.refreshed: list[object] = []

    async def scalar(self, statement):  # noqa: ANN001
        self.scalar_statements.append(statement)
        if self.scalar_results:
            return self.scalar_results.pop(0)
        return None

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def delete(self, obj: object) -> None:
        self.deleted.append(obj)

    async def commit(self) -> None:
        self.commits += 1

    async def refresh(self, obj: object) -> None:
        self.refreshed.append(obj)


def make_user(user_id: str = "user-1") -> SimpleNamespace:
    return SimpleNamespace(id=user_id)


def make_binding(**overrides: object) -> UserTelegramBindingModel:
    values = {
        "user_id": "user-1",
        "telegram_chat_id": "123",
        "username": "old_user",
    }
    values.update(overrides)
    return UserTelegramBindingModel(**values)


class TelegramBindingSchemaTests(unittest.TestCase):
    def test_upsert_normalizes_chat_id_and_username(self) -> None:
        payload = TelegramBindingUpsert(telegram_chat_id=" 123 ", username="@auction_user ")

        self.assertEqual(payload.telegram_chat_id, "123")
        self.assertEqual(payload.username, "auction_user")


class TelegramBindingServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_returns_current_user_binding(self) -> None:
        session = FakeSession([make_binding()])
        service = TelegramBindingService()

        response = await service.get_for_user(session, make_user())

        self.assertIsNotNone(response)
        self.assertEqual(response.user_id, "user-1")
        self.assertEqual(response.telegram_chat_id, "123")

    async def test_upsert_creates_new_binding(self) -> None:
        session = FakeSession([None])
        service = TelegramBindingService()

        response = await service.upsert_for_user(
            session,
            make_user(),
            TelegramBindingUpsert(telegram_chat_id="456", username="new_user"),
        )

        self.assertEqual(response.user_id, "user-1")
        self.assertEqual(response.telegram_chat_id, "456")
        self.assertEqual(len(session.added), 1)
        self.assertEqual(session.commits, 1)
        self.assertEqual(session.refreshed, session.added)

    async def test_upsert_updates_existing_binding(self) -> None:
        binding = make_binding()
        session = FakeSession([binding])
        service = TelegramBindingService()

        response = await service.upsert_for_user(
            session,
            make_user(),
            TelegramBindingUpsert(telegram_chat_id="789", username=None),
        )

        self.assertEqual(response.telegram_chat_id, "789")
        self.assertIsNone(response.username)
        self.assertEqual(binding.telegram_chat_id, "789")
        self.assertEqual(session.added, [])
        self.assertEqual(session.commits, 1)

    async def test_delete_is_idempotent_for_current_user(self) -> None:
        service = TelegramBindingService()
        missing_session = FakeSession([None])

        await service.delete_for_user(missing_session, make_user())

        self.assertEqual(missing_session.deleted, [])
        self.assertEqual(missing_session.commits, 0)

        binding = make_binding()
        existing_session = FakeSession([binding])
        await service.delete_for_user(existing_session, make_user())

        self.assertEqual(existing_session.deleted, [binding])
        self.assertEqual(existing_session.commits, 1)


if __name__ == "__main__":
    unittest.main()
