from __future__ import annotations

import asyncio
import logging

from app.core.config import get_settings
from app.infrastructure.db.database import AsyncSessionLocal
from app.services.telegram_sender import send_pending_telegram_notifications
from app.worker.safety import safe_worker_sleep_seconds


logger = logging.getLogger(__name__)
settings = get_settings()


async def run_sender_batch() -> dict[str, int]:
    async with AsyncSessionLocal() as session:
        result = await send_pending_telegram_notifications(
            session,
            bot_token=settings.telegram_bot_token,
            chat_id=settings.telegram_chat_id,
            limit=settings.telegram_sender_batch_limit,
            dry_run=settings.telegram_sender_dry_run,
            max_attempts=settings.telegram_sender_max_attempts,
            base_backoff_seconds=settings.telegram_sender_base_backoff_seconds,
        )
        await session.commit()
    payload = result.model_dump(mode="json")
    logger.info("Telegram sender batch completed: %s", payload)
    return payload


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
