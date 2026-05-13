from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

from app.models import TelegramConnectTokenModel
from app.services.telegram_connect import (
    TELEGRAM_START_PREFIX,
    TelegramConnectError,
    TelegramConnectService,
    build_connect_url,
    hash_connect_token,
)


class FakeSession:
    def __init__(self, scalar_results: list[object | None] | None = None) -> None:
        self.scalar_results = list(scalar_results or [])
        self.scalar_statements = []
        self.added: list[object] = []
        self.commits = 0
        self.refreshed: list[object] = []

    async def scalar(self, statement):  # noqa: ANN001
        self.scalar_statements.append(statement)
        if self.scalar_results:
            return self.scalar_results.pop(0)
        return None

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.commits += 1

    async def refresh(self, obj: object) -> None:
        self.refreshed.append(obj)


def make_user(user_id: str = "user-1") -> SimpleNamespace:
    return SimpleNamespace(id=user_id)


def make_token_record(**overrides: object) -> TelegramConnectTokenModel:
    values = {
        "id": "token-record-1",
        "user_id": "user-1",
        "token_hash": hash_connect_token("plain-token"),
        "expires_at": datetime.now(UTC) + timedelta(minutes=5),
        "used_at": None,
    }
    values.update(overrides)
    return TelegramConnectTokenModel(**values)


class TelegramConnectHelpersTests(unittest.TestCase):
    def test_build_connect_url_normalizes_bot_username(self) -> None:
        url = build_connect_url("@auction_bot", "abc_123")

        self.assertEqual(url, "https://t.me/auction_bot?start=connect_abc_123")

    def test_build_connect_url_rejects_missing_username(self) -> None:
        with self.assertRaises(TelegramConnectError):
            build_connect_url(" ", "abc")

    def test_build_connect_url_rejects_too_long_start_payload(self) -> None:
        with self.assertRaises(TelegramConnectError):
            build_connect_url("auction_bot", "a" * 65)


class TelegramConnectServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_connect_token_persists_hash_and_returns_deep_link(self) -> None:
        session = FakeSession()
        service = TelegramConnectService()

        response = await service.create_connect_token(
            session,
            make_user(),
            bot_username="auction_bot",
            ttl_seconds=600,
        )

        self.assertEqual(len(session.added), 1)
        self.assertEqual(session.commits, 1)
        record = session.added[0]
        self.assertIsInstance(record, TelegramConnectTokenModel)
        self.assertEqual(record.user_id, "user-1")
        self.assertEqual(len(record.token_hash), 64)
        self.assertLess(datetime.now(UTC), response.expires_at)

        parsed = urlparse(response.connect_url)
        self.assertEqual(parsed.netloc, "t.me")
        self.assertEqual(parsed.path, "/auction_bot")
        start_payload = parse_qs(parsed.query)["start"][0]
        self.assertTrue(start_payload.startswith(TELEGRAM_START_PREFIX))
        raw_token = start_payload.removeprefix(TELEGRAM_START_PREFIX)
        self.assertEqual(record.token_hash, hash_connect_token(raw_token))

    async def test_create_connect_token_requires_bot_username(self) -> None:
        service = TelegramConnectService()

        with self.assertRaises(TelegramConnectError):
            await service.create_connect_token(
                FakeSession(),
                make_user(),
                bot_username=None,
                ttl_seconds=600,
            )

    async def test_consume_connect_token_marks_valid_record_used(self) -> None:
        record = make_token_record()
        session = FakeSession([record])
        service = TelegramConnectService()

        consumed = await service.consume_connect_token(session, "plain-token")

        self.assertIs(consumed, record)
        self.assertIsNotNone(record.used_at)
        self.assertEqual(session.commits, 1)
        self.assertEqual(session.refreshed, [record])

    async def test_consume_connect_token_rejects_missing_used_or_expired_record(self) -> None:
        service = TelegramConnectService()

        missing = await service.consume_connect_token(FakeSession([None]), "plain-token")
        self.assertIsNone(missing)

        used = make_token_record(used_at=datetime.now(UTC))
        used_response = await service.consume_connect_token(FakeSession([used]), "plain-token")
        self.assertIsNone(used_response)

        expired = make_token_record(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        expired_response = await service.consume_connect_token(FakeSession([expired]), "plain-token")
        self.assertIsNone(expired_response)


if __name__ == "__main__":
    unittest.main()
