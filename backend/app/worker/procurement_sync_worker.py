from __future__ import annotations

import asyncio
import logging
import random

from app.core.config import get_settings
from app.infrastructure.db.database import AsyncSessionLocal
from app.services.procurement_sync import sync_enabled_procurement_sources
from app.worker.safety import safe_worker_jitter_delay


logger = logging.getLogger(__name__)
settings = get_settings()


def calculate_next_sync_delay() -> float:
    return safe_worker_jitter_delay(
        settings.procurement_sync_interval_seconds,
        settings.procurement_sync_interval_jitter_seconds,
        random_fraction=random.random,
    )


async def run_worker(*, run_once: bool = False) -> None:
    logger.info("Procurement sync worker started")
    try:
        if not settings.procurement_sync_run_on_start:
            delay = calculate_next_sync_delay()
            logger.info("Initial procurement sync delayed for %.0f seconds", delay)
            await asyncio.sleep(delay)
        while True:
            if settings.procurement_sync_enabled:
                limit = settings.procurement_sync_limit if settings.procurement_sync_limit > 0 else None
                async with AsyncSessionLocal() as session:
                    await sync_enabled_procurement_sources(session, limit=limit)
            else:
                logger.info("Procurement sync worker disabled")
            if run_once:
                return
            delay = calculate_next_sync_delay()
            logger.info("Next procurement sync in %.0f seconds", delay)
            await asyncio.sleep(delay)
    except asyncio.CancelledError:
        logger.info("Procurement sync worker shutdown requested")
        raise


def main() -> None:
    logging.basicConfig(level=settings.debug_level)
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
