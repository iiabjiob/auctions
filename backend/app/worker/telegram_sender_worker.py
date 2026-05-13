from __future__ import annotations

import asyncio
import logging

from app.core.config import get_settings
from app.infrastructure.db.database import AsyncSessionLocal
from app.services.telegram_sender import TelegramSenderBatchResult, send_pending_procurement_telegram_notifications, send_pending_telegram_notifications
from app.worker.safety import safe_worker_sleep_seconds


logger = logging.getLogger(__name__)
settings = get_settings()


async def run_sender_batch() -> dict[str, int]:
    async with AsyncSessionLocal() as session:
        auction_result = await send_pending_telegram_notifications(
            session,
            bot_token=settings.telegram_bot_token,
            chat_id=settings.telegram_chat_id,
            limit=settings.telegram_sender_batch_limit,
            dry_run=settings.telegram_sender_dry_run,
            max_attempts=settings.telegram_sender_max_attempts,
            base_backoff_seconds=settings.telegram_sender_base_backoff_seconds,
        )
        remaining_limit = max(0, settings.telegram_sender_batch_limit - auction_result.selected)
        procurement_result = await send_pending_procurement_telegram_notifications(
            session,
            bot_token=settings.telegram_bot_token,
            chat_id=settings.telegram_chat_id,
            limit=remaining_limit,
            dry_run=settings.telegram_sender_dry_run,
            max_attempts=settings.telegram_sender_max_attempts,
            base_backoff_seconds=settings.telegram_sender_base_backoff_seconds,
        )
        await session.commit()
    result = _merge_batch_results(auction_result, procurement_result)
    payload = result.model_dump(mode="json")
    logger.info("Telegram sender batch completed: %s", payload)
    return payload


def _merge_batch_results(first: TelegramSenderBatchResult, second: TelegramSenderBatchResult) -> TelegramSenderBatchResult:
    return TelegramSenderBatchResult(
        selected=first.selected + second.selected,
        sent=first.sent + second.sent,
        failed=first.failed + second.failed,
        retried=first.retried + second.retried,
        dry_run=first.dry_run + second.dry_run,
    )


async def run_worker(*, run_once: bool = False) -> dict[str, int] | None:
    logger.info("Telegram sender worker started")
    try:
        while True:
            result = await run_sender_batch()
            if run_once:
                return result
            await asyncio.sleep(safe_worker_sleep_seconds(settings.telegram_sender_poll_interval_seconds))
    except asyncio.CancelledError:
        logger.info("Telegram sender worker shutdown requested")
        raise


def main() -> None:
    logging.basicConfig(level=settings.debug_level)
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("Telegram sender worker stopped by interrupt")


if __name__ == "__main__":
    main()
