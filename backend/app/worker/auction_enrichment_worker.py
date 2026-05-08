from __future__ import annotations

import asyncio
import logging

from app.core.config import get_settings
from app.infrastructure.db.database import AsyncSessionLocal
from app.services.lot_enrichment import DEFAULT_ENRICHMENT_CANDIDATE_LIMIT, execute_lot_enrichment_candidates


logger = logging.getLogger(__name__)
settings = get_settings()


async def run_enrichment_batch() -> dict[str, object]:
    async with AsyncSessionLocal() as session:
        result = await execute_lot_enrichment_candidates(
            session,
            limit=settings.auction_enrichment_batch_size or DEFAULT_ENRICHMENT_CANDIDATE_LIMIT,
        )
    logger.info("Auction enrichment completed: %s", result.model_dump(mode="json"))
    return result.model_dump(mode="json")


async def run_worker(*, run_once: bool = False) -> dict[str, object] | None:
    logger.info("Auction enrichment worker started")
    try:
        while True:
            if not settings.auction_enrichment_enabled:
                if run_once:
                    return None
                await asyncio.sleep(max(1, settings.auction_enrichment_interval_seconds))
                continue

            result = await run_enrichment_batch()
            if run_once:
                return result
            await asyncio.sleep(max(1, settings.auction_enrichment_interval_seconds))
    except asyncio.CancelledError:
        logger.info("Auction enrichment worker shutdown requested")
        raise


def main() -> None:
    logging.basicConfig(level=settings.debug_level)
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("Auction enrichment worker stopped by interrupt")


if __name__ == "__main__":
    main()
