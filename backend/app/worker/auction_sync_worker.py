from __future__ import annotations

import asyncio
import logging

from app.core.config import get_settings
from app.infrastructure.db.database import AsyncSessionLocal
from app.infrastructure.redis.streams import publish_auction_event
from app.services.auction_sources import SOURCE_PROVIDERS
from app.services.auction_sync import sync_source_lots


logger = logging.getLogger(__name__)
settings = get_settings()


async def sync_all_sources() -> None:
    for source_code in SOURCE_PROVIDERS:
        await publish_auction_event("sync.started", {"source": source_code})
        try:
            sync_limit = settings.auction_sync_limit if settings.auction_sync_limit > 0 else None

            async def publish_sync_progress(payload: dict) -> None:
                await publish_auction_event("sync.progress", payload)

            async with AsyncSessionLocal() as session:
                result = await sync_source_lots(
                    session,
                    source=source_code,
                    limit=sync_limit,
                    on_progress=publish_sync_progress,
                )
            await publish_auction_event("sync.completed", result.model_dump(mode="json"))
            logger.info("Synced source %s: %s", source_code, result.model_dump(mode="json"))
        except Exception as error:
            logger.exception("Failed to sync source %s", source_code)
            await publish_auction_event("sync.failed", {"source": source_code, "error": str(error)})


async def run_worker() -> None:
    logger.info("Auction sync worker started")
    while True:
        await sync_all_sources()
        await asyncio.sleep(settings.auction_sync_interval_seconds)


def main() -> None:
    logging.basicConfig(level=settings.debug_level)
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()