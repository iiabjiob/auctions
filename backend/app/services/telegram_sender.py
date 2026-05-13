from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from sqlalchemy import case, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auction import TelegramNotificationOutbox
from app.models.procurement import ProcurementTelegramNotificationOutbox
from app.schemas.lot_decision_report import TelegramNotificationStatus


TELEGRAM_SEND_MESSAGE_URL_TEMPLATE = "https://api.telegram.org/bot{bot_token}/sendMessage"
TELEGRAM_SEND_PHOTO_URL_TEMPLATE = "https://api.telegram.org/bot{bot_token}/sendPhoto"


class TelegramSenderError(Exception):
    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


class TelegramMessageSender(Protocol):
    async def send_message(
        self,
        *,
        bot_token: str,
        chat_id: str,
        text: str,
        parse_mode: str,
    ) -> None:
        ...

    async def send_photo(
        self,
        *,
        bot_token: str,
        chat_id: str,
        photo_url: str,
        caption: str,
        parse_mode: str,
    ) -> None:
        ...


@dataclass(frozen=True)
class TelegramSenderBatchResult:
    selected: int = 0
    sent: int = 0
    failed: int = 0
    retried: int = 0
    dry_run: int = 0

    def model_dump(self, mode: str = "python") -> dict[str, int]:  # noqa: ARG002
        return {
            "selected": self.selected,
            "sent": self.sent,
            "failed": self.failed,
            "retried": self.retried,
            "dry_run": self.dry_run,
        }


class TelegramBotApiSender:
    def __init__(self, *, timeout_seconds: float = 10.0) -> None:
        self.timeout_seconds = timeout_seconds

    async def send_message(
        self,
        *,
        bot_token: str,
        chat_id: str,
        text: str,
        parse_mode: str,
    ) -> None:
        await asyncio.to_thread(
            self._send_message_sync,
            bot_token=bot_token,
            chat_id=chat_id,
            text=text,
            parse_mode=parse_mode,
        )

    def _send_message_sync(self, *, bot_token: str, chat_id: str, text: str, parse_mode: str) -> None:
        payload = json.dumps(
            {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            }
        ).encode("utf-8")
        request = Request(
            TELEGRAM_SEND_MESSAGE_URL_TEMPLATE.format(bot_token=bot_token),
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        self._post_request(request)

    async def send_photo(
        self,
        *,
        bot_token: str,
        chat_id: str,
        photo_url: str,
        caption: str,
        parse_mode: str,
    ) -> None:
        await asyncio.to_thread(
            self._send_photo_sync,
            bot_token=bot_token,
            chat_id=chat_id,
            photo_url=photo_url,
            caption=caption,
            parse_mode=parse_mode,
        )

    def _send_photo_sync(self, *, bot_token: str, chat_id: str, photo_url: str, caption: str, parse_mode: str) -> None:
        payload = json.dumps(
            {
                "chat_id": chat_id,
                "photo": photo_url,
                "caption": caption,
                "parse_mode": parse_mode,
            }
        ).encode("utf-8")
        request = Request(
            TELEGRAM_SEND_PHOTO_URL_TEMPLATE.format(bot_token=bot_token),
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        self._post_request(request)

    def _post_request(self, request: Request) -> None:
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            retryable = error.code == 429 or 500 <= error.code < 600
            raise TelegramSenderError(_telegram_http_error_message(error), retryable=retryable) from error
        except (TimeoutError, URLError, OSError) as error:
            raise TelegramSenderError(str(error) or "Telegram request failed", retryable=True) from error
        if not isinstance(response_payload, dict) or not response_payload.get("ok"):
            description = response_payload.get("description") if isinstance(response_payload, dict) else None
            raise TelegramSenderError(description or "Telegram API returned unsuccessful response", retryable=False)


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


async def send_pending_telegram_notifications(
    session: AsyncSession,
    *,
    bot_token: str | None,
    chat_id: str | None,
    limit: int,
    dry_run: bool,
    sender: TelegramMessageSender | None = None,
    max_attempts: int = 3,
    base_backoff_seconds: int = 60,
    now: datetime | None = None,
) -> TelegramSenderBatchResult:
    if limit <= 0:
        return TelegramSenderBatchResult()
    current_time = now or datetime.now(UTC)
    entries = await _pending_entries(session, limit=limit, now=current_time)
    if not entries:
        return TelegramSenderBatchResult()
    if dry_run:
        return TelegramSenderBatchResult(selected=len(entries), dry_run=len(entries))
    if not bot_token:
        raise ValueError("telegram_bot_token is required when dry-run is disabled")

    resolved_sender = sender or TelegramBotApiSender()
    sent = 0
    failed = 0
    retried = 0
    for entry in entries:
        message_payload = entry.message_payload if isinstance(entry.message_payload, dict) else {}
        target_chat_id = _target_chat_id(entry, fallback_chat_id=chat_id)
        if target_chat_id is None:
            _mark_retry_or_failed(
                entry,
                message="Telegram chat_id is not configured for notification",
                retryable=False,
                max_attempts=max_attempts,
                base_backoff_seconds=base_backoff_seconds,
                now=current_time,
            )
            failed += 1
            continue
        try:
            photo_url = str(message_payload.get("photo_url") or "").strip()
            if photo_url.startswith(("http://", "https://")):
                await resolved_sender.send_photo(
                    bot_token=bot_token,
                    chat_id=target_chat_id,
                    photo_url=photo_url,
                    caption=str(message_payload.get("text") or ""),
                    parse_mode=str(message_payload.get("parse_mode") or "MarkdownV2"),
                )
            else:
                await resolved_sender.send_message(
                    bot_token=bot_token,
                    chat_id=target_chat_id,
                    text=str(message_payload.get("text") or ""),
                    parse_mode=str(message_payload.get("parse_mode") or "MarkdownV2"),
                )
        except TelegramSenderError as error:
            retryable = error.retryable
            if _mark_retry_or_failed(
                entry,
                message=str(error),
                retryable=retryable,
                max_attempts=max_attempts,
                base_backoff_seconds=base_backoff_seconds,
                now=current_time,
            ):
                retried += 1
            else:
                failed += 1
            continue
        except Exception as error:
            if _mark_retry_or_failed(
                entry,
                message=str(error) or "Unexpected Telegram sender error",
                retryable=True,
                max_attempts=max_attempts,
                base_backoff_seconds=base_backoff_seconds,
                now=current_time,
            ):
                retried += 1
            else:
                failed += 1
            continue

        _mark_sent(entry, now=current_time)
        sent += 1

    await session.flush()
    return TelegramSenderBatchResult(selected=len(entries), sent=sent, failed=failed, retried=retried)


async def send_pending_procurement_telegram_notifications(
    session: AsyncSession,
    *,
    bot_token: str | None,
    chat_id: str | None,
    limit: int,
    dry_run: bool,
    sender: TelegramMessageSender | None = None,
    max_attempts: int = 3,
    base_backoff_seconds: int = 60,
    now: datetime | None = None,
) -> TelegramSenderBatchResult:
    if limit <= 0:
        return TelegramSenderBatchResult()
    current_time = now or datetime.now(UTC)
    entries = await _pending_procurement_entries(session, limit=limit, now=current_time)
    if not entries:
        return TelegramSenderBatchResult()
    if dry_run:
        return TelegramSenderBatchResult(selected=len(entries), dry_run=len(entries))
    if not bot_token:
        raise ValueError("telegram_bot_token is required when dry-run is disabled")

    resolved_sender = sender or TelegramBotApiSender()
    sent = 0
    failed = 0
    retried = 0
    for entry in entries:
        message_payload = entry.message_payload if isinstance(entry.message_payload, dict) else {}
        target_chat_id = _target_chat_id(entry, fallback_chat_id=chat_id)
        if target_chat_id is None:
            _mark_retry_or_failed(
                entry,
                message="Telegram chat_id is not configured for notification",
                retryable=False,
                max_attempts=max_attempts,
                base_backoff_seconds=base_backoff_seconds,
                now=current_time,
            )
            failed += 1
            continue
        try:
            photo_url = str(message_payload.get("photo_url") or "").strip()
            if photo_url.startswith(("http://", "https://")):
                await resolved_sender.send_photo(
                    bot_token=bot_token,
                    chat_id=target_chat_id,
                    photo_url=photo_url,
                    caption=str(message_payload.get("text") or ""),
                    parse_mode=str(message_payload.get("parse_mode") or "MarkdownV2"),
                )
            else:
                await resolved_sender.send_message(
                    bot_token=bot_token,
                    chat_id=target_chat_id,
                    text=str(message_payload.get("text") or ""),
                    parse_mode=str(message_payload.get("parse_mode") or "MarkdownV2"),
                )
        except TelegramSenderError as error:
            if _mark_retry_or_failed(
                entry,
                message=str(error),
                retryable=error.retryable,
                max_attempts=max_attempts,
                base_backoff_seconds=base_backoff_seconds,
                now=current_time,
            ):
                retried += 1
            else:
                failed += 1
            continue
        except Exception as error:
            if _mark_retry_or_failed(
                entry,
                message=str(error) or "Unexpected Telegram sender error",
                retryable=True,
                max_attempts=max_attempts,
                base_backoff_seconds=base_backoff_seconds,
                now=current_time,
            ):
                retried += 1
            else:
                failed += 1
            continue

        _mark_sent(entry, now=current_time)
        sent += 1

    await session.flush()
    return TelegramSenderBatchResult(selected=len(entries), sent=sent, failed=failed, retried=retried)


async def _pending_entries(session: AsyncSession, *, limit: int, now: datetime) -> list[TelegramNotificationOutbox]:
    priority_order = case(
        (TelegramNotificationOutbox.priority == "urgent", 0),
        (TelegramNotificationOutbox.priority == "high", 1),
        (TelegramNotificationOutbox.priority == "medium", 2),
        else_=3,
    )
    statement = (
        select(TelegramNotificationOutbox)
        .where(TelegramNotificationOutbox.status == TelegramNotificationStatus.PENDING.value)
        .where(
            or_(
                TelegramNotificationOutbox.next_attempt_at.is_(None),
                TelegramNotificationOutbox.next_attempt_at <= now,
            )
        )
        .order_by(priority_order, TelegramNotificationOutbox.scheduled_at.asc(), TelegramNotificationOutbox.id.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    return list((await session.scalars(statement)).all())


def _target_chat_id(entry: TelegramNotificationOutbox, *, fallback_chat_id: str | None) -> str | None:
    entry_chat_id = str(entry.telegram_chat_id or "").strip()
    if entry_chat_id:
        return entry_chat_id
    fallback = str(fallback_chat_id or "").strip()
    return fallback or None


async def _pending_procurement_entries(
    session: AsyncSession,
    *,
    limit: int,
    now: datetime,
) -> list[ProcurementTelegramNotificationOutbox]:
    priority_order = case(
        (ProcurementTelegramNotificationOutbox.priority == "urgent", 0),
        (ProcurementTelegramNotificationOutbox.priority == "high", 1),
        (ProcurementTelegramNotificationOutbox.priority == "medium", 2),
        else_=3,
    )
    statement = (
        select(ProcurementTelegramNotificationOutbox)
        .where(ProcurementTelegramNotificationOutbox.status == TelegramNotificationStatus.PENDING.value)
        .where(
            or_(
                ProcurementTelegramNotificationOutbox.next_attempt_at.is_(None),
                ProcurementTelegramNotificationOutbox.next_attempt_at <= now,
            )
        )
        .order_by(priority_order, ProcurementTelegramNotificationOutbox.scheduled_at.asc(), ProcurementTelegramNotificationOutbox.id.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    return list((await session.scalars(statement)).all())


def _mark_sent(entry: TelegramNotificationOutbox, *, now: datetime) -> None:
    entry.status = TelegramNotificationStatus.SENT.value
    entry.sent_at = now
    entry.failed_at = None
    entry.next_attempt_at = None
    entry.last_error = None
    entry.updated_at = now


def _mark_retry_or_failed(
    entry: TelegramNotificationOutbox,
    *,
    message: str,
    retryable: bool,
    max_attempts: int,
    base_backoff_seconds: int,
    now: datetime,
) -> bool:
    entry.attempt_count = int(entry.attempt_count or 0) + 1
    entry.last_error = message[:2000]
    entry.updated_at = now
    if retryable and entry.attempt_count < max(1, max_attempts):
        entry.status = TelegramNotificationStatus.PENDING.value
        entry.next_attempt_at = now + timedelta(seconds=_backoff_seconds(entry.attempt_count, base_backoff_seconds))
        return True
    entry.status = TelegramNotificationStatus.FAILED.value
    entry.failed_at = now
    entry.next_attempt_at = None
    return False


def _backoff_seconds(attempt_count: int, base_backoff_seconds: int) -> int:
    return max(1, base_backoff_seconds) * (2 ** max(0, attempt_count - 1))
