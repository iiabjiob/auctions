from __future__ import annotations

import unittest
from io import BytesIO
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.error import HTTPError
from unittest.mock import AsyncMock, patch

from app.models.auction import TelegramNotificationOutbox
from app.schemas.lot_decision_report import TelegramNotificationStatus
from app.services.telegram_sender import (
    TelegramBotApiSender,
    TelegramSenderBatchResult,
    TelegramSenderError,
    send_pending_telegram_notifications,
)
from app.worker import telegram_sender_worker


NOW = datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc)


class FakeScalarResult:
    def __init__(self, values: list[object]) -> None:
        self._values = values

    def all(self) -> list[object]:
        return self._values


class FakeSession:
    def __init__(self, entries: list[TelegramNotificationOutbox] | None = None) -> None:
        self.entries = list(entries or [])
        self.statements = []
        self.flushes = 0
        self.commits = 0

    async def scalars(self, statement):  # noqa: ANN001
        self.statements.append(statement)
        return FakeScalarResult(self.entries)

    async def flush(self) -> None:
        self.flushes += 1

    async def commit(self) -> None:
        self.commits += 1


class FakeSessionContext:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    async def __aenter__(self) -> FakeSession:
        return self.session

    async def __aexit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        return None


class FakeSender:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[dict[str, str]] = []

    async def send_message(self, *, bot_token: str, chat_id: str, text: str, parse_mode: str) -> None:
        self.calls.append(
            {
                "method": "send_message",
                "bot_token": bot_token,
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
            }
        )
        if self.error is not None:
            raise self.error

    async def send_photo(self, *, bot_token: str, chat_id: str, photo_url: str, caption: str, parse_mode: str) -> None:
        self.calls.append(
            {
                "method": "send_photo",
                "bot_token": bot_token,
                "chat_id": chat_id,
                "photo_url": photo_url,
                "caption": caption,
                "parse_mode": parse_mode,
            }
        )
        if self.error is not None:
            raise self.error


def make_entry(**overrides: object) -> TelegramNotificationOutbox:
    values = {
        "id": 1,
        "lot_record_id": 1,
        "decision_report_id": 10,
        "dedupe_key": "dedupe-1",
        "cooldown_key": "cooldown-1",
        "status": TelegramNotificationStatus.PENDING.value,
        "priority": "high",
        "message_payload": {"text": "Lot message", "parse_mode": "HTML"},
        "report_hash": "report-hash",
        "scheduled_at": NOW,
        "cooldown_until": NOW + timedelta(hours=6),
        "attempt_count": 0,
    }
    values.update(overrides)
    return TelegramNotificationOutbox(**values)


class TelegramSenderTests(unittest.IsolatedAsyncioTestCase):
    async def test_bot_api_sender_includes_telegram_error_description(self) -> None:
        response = BytesIO(b'{"ok": false, "error_code": 400, "description": "Bad Request: chat not found"}')
        error = HTTPError(
            url="https://api.telegram.org/botTOKEN/sendMessage",
            code=400,
            msg="Bad Request",
            hdrs={},
            fp=response,
        )

        with patch("app.services.telegram_sender.urlopen", side_effect=error):
            with self.assertRaises(TelegramSenderError) as context:
                await TelegramBotApiSender().send_message(
                    bot_token="TOKEN",
                    chat_id="@missing",
                    text="hello",
                    parse_mode="HTML",
                )

        self.assertEqual(str(context.exception), "Telegram HTTP 400: Bad Request: chat not found")
        self.assertFalse(context.exception.retryable)

    async def test_successful_send_marks_entry_sent(self) -> None:
        entry = make_entry(telegram_chat_id="chat")
        sender = FakeSender()
        session = FakeSession([entry])

        result = await send_pending_telegram_notifications(
            session,
            bot_token="token",
            chat_id="chat",
            limit=10,
            dry_run=False,
            sender=sender,
            now=NOW,
        )

        self.assertEqual(result, TelegramSenderBatchResult(selected=1, sent=1))
        self.assertEqual(entry.status, "sent")
        self.assertEqual(entry.sent_at, NOW)
        self.assertIsNone(entry.next_attempt_at)
        self.assertEqual(sender.calls[0]["bot_token"], "token")
        self.assertEqual(sender.calls[0]["method"], "send_message")
        self.assertEqual(sender.calls[0]["chat_id"], "chat")
        self.assertEqual(sender.calls[0]["text"], "Lot message")
        self.assertEqual(session.flushes, 1)

    async def test_photo_payload_sends_photo_with_caption(self) -> None:
        entry = make_entry(
            telegram_chat_id="chat",
            message_payload={"text": "Lot message", "parse_mode": "MarkdownV2", "photo_url": "https://example.test/lot.jpg"},
        )
        sender = FakeSender()
        session = FakeSession([entry])

        result = await send_pending_telegram_notifications(
            session,
            bot_token="token",
            chat_id="chat",
            limit=10,
            dry_run=False,
            sender=sender,
            now=NOW,
        )

        self.assertEqual(result, TelegramSenderBatchResult(selected=1, sent=1))
        self.assertEqual(sender.calls[0]["method"], "send_photo")
        self.assertEqual(sender.calls[0]["photo_url"], "https://example.test/lot.jpg")
        self.assertEqual(sender.calls[0]["caption"], "Lot message")
        self.assertEqual(entry.status, "sent")

    async def test_per_entry_chat_id_overrides_global_chat_id(self) -> None:
        entry = make_entry(telegram_chat_id="personal-chat")
        sender = FakeSender()
        session = FakeSession([entry])

        result = await send_pending_telegram_notifications(
            session,
            bot_token="token",
            chat_id="global-chat",
            limit=10,
            dry_run=False,
            sender=sender,
            now=NOW,
        )

        self.assertEqual(result, TelegramSenderBatchResult(selected=1, sent=1))
        self.assertEqual(sender.calls[0]["chat_id"], "personal-chat")
        self.assertEqual(entry.status, "sent")

    async def test_global_chat_id_is_not_used_for_legacy_entries(self) -> None:
        entry = make_entry(telegram_chat_id=None)
        sender = FakeSender()
        session = FakeSession([entry])

        result = await send_pending_telegram_notifications(
            session,
            bot_token="token",
            chat_id="global-chat",
            limit=10,
            dry_run=False,
            sender=sender,
            now=NOW,
        )

        self.assertEqual(result, TelegramSenderBatchResult(selected=1, failed=1))
        self.assertEqual(sender.calls, [])
        self.assertEqual(entry.status, "failed")

    async def test_missing_chat_id_fails_entry_without_crashing_batch(self) -> None:
        entry = make_entry(telegram_chat_id=None)
        sender = FakeSender()
        session = FakeSession([entry])

        result = await send_pending_telegram_notifications(
            session,
            bot_token="token",
            chat_id=None,
            limit=10,
            dry_run=False,
            sender=sender,
            now=NOW,
        )

        self.assertEqual(result, TelegramSenderBatchResult(selected=1, failed=1))
        self.assertEqual(sender.calls, [])
        self.assertEqual(entry.status, "failed")
        self.assertEqual(entry.last_error, "Telegram chat_id is not configured for notification")
        self.assertEqual(entry.failed_at, NOW)
        self.assertEqual(session.flushes, 1)

    async def test_dry_run_does_not_send_or_mutate_entry(self) -> None:
        entry = make_entry()
        sender = FakeSender()
        session = FakeSession([entry])

        result = await send_pending_telegram_notifications(
            session,
            bot_token=None,
            chat_id=None,
            limit=10,
            dry_run=True,
            sender=sender,
            now=NOW,
        )

        self.assertEqual(result, TelegramSenderBatchResult(selected=1, dry_run=1))
        self.assertEqual(sender.calls, [])
        self.assertEqual(entry.status, "pending")
        self.assertEqual(entry.attempt_count, 0)
        self.assertEqual(session.flushes, 0)

    async def test_zero_limit_selects_nothing(self) -> None:
        entry = make_entry()
        sender = FakeSender()
        session = FakeSession([entry])

        result = await send_pending_telegram_notifications(
            session,
            bot_token="token",
            chat_id="chat",
            limit=0,
            dry_run=False,
            sender=sender,
            now=NOW,
        )

        self.assertEqual(result, TelegramSenderBatchResult())
        self.assertEqual(session.statements, [])
        self.assertEqual(sender.calls, [])

    async def test_retryable_failure_schedules_backoff(self) -> None:
        entry = make_entry(telegram_chat_id="chat")
        sender = FakeSender(TelegramSenderError("rate limited", retryable=True))
        session = FakeSession([entry])

        result = await send_pending_telegram_notifications(
            session,
            bot_token="token",
            chat_id="chat",
            limit=10,
            dry_run=False,
            sender=sender,
            max_attempts=3,
            base_backoff_seconds=60,
            now=NOW,
        )

        self.assertEqual(result, TelegramSenderBatchResult(selected=1, retried=1))
        self.assertEqual(entry.status, "pending")
        self.assertEqual(entry.attempt_count, 1)
        self.assertEqual(entry.next_attempt_at, NOW + timedelta(seconds=60))
        self.assertEqual(entry.last_error, "rate limited")
        self.assertEqual(session.flushes, 1)

    async def test_exhausted_retry_marks_failed(self) -> None:
        entry = make_entry(attempt_count=2)
        sender = FakeSender(TelegramSenderError("server error", retryable=True))
        session = FakeSession([entry])

        result = await send_pending_telegram_notifications(
            session,
            bot_token="token",
            chat_id="chat",
            limit=10,
            dry_run=False,
            sender=sender,
            max_attempts=3,
            base_backoff_seconds=60,
            now=NOW,
        )

        self.assertEqual(result, TelegramSenderBatchResult(selected=1, failed=1))
        self.assertEqual(entry.status, "failed")
        self.assertEqual(entry.attempt_count, 3)
        self.assertEqual(entry.failed_at, NOW)
        self.assertIsNone(entry.next_attempt_at)

    async def test_worker_reads_config_and_commits_batch(self) -> None:
        session = FakeSession()
        settings = SimpleNamespace(
            telegram_bot_token="token",
            telegram_sender_batch_limit=7,
            telegram_sender_dry_run=True,
            telegram_sender_max_attempts=4,
            telegram_sender_base_backoff_seconds=30,
        )
        result = TelegramSenderBatchResult(selected=1, dry_run=1)
        procurement_result = TelegramSenderBatchResult(selected=2, sent=1)

        with (
            patch.object(telegram_sender_worker, "settings", settings),
            patch.object(telegram_sender_worker, "AsyncSessionLocal", return_value=FakeSessionContext(session)),
            patch.object(telegram_sender_worker, "send_pending_telegram_notifications", AsyncMock(return_value=result)) as send_batch,
            patch.object(
                telegram_sender_worker,
                "send_pending_procurement_telegram_notifications",
                AsyncMock(return_value=procurement_result),
            ) as send_procurement_batch,
        ):
            payload = await telegram_sender_worker.run_sender_batch()

        self.assertEqual(payload, {"selected": 3, "sent": 1, "failed": 0, "retried": 0, "dry_run": 1})
        self.assertEqual(session.commits, 1)
        send_batch.assert_awaited_once()
        self.assertEqual(send_batch.await_args.kwargs["bot_token"], "token")
        self.assertEqual(send_batch.await_args.kwargs["limit"], 7)
        self.assertTrue(send_batch.await_args.kwargs["dry_run"])
        send_procurement_batch.assert_awaited_once()
        self.assertEqual(send_procurement_batch.await_args.kwargs["bot_token"], "token")
        self.assertEqual(send_procurement_batch.await_args.kwargs["limit"], 7)
        self.assertTrue(send_procurement_batch.await_args.kwargs["dry_run"])


if __name__ == "__main__":
    unittest.main()
