from __future__ import annotations

import asyncio
import logging

from app.core.config import get_settings
from app.infrastructure.db.database import AsyncSessionLocal
from app.services.lot_enrichment import DEFAULT_ENRICHMENT_CANDIDATE_LIMIT, dry_run_lot_enrichment_candidates


logger = logging.getLogger(__name__)
settings = get_settings()


async def run_worker() -> dict[str, object]:
    logger.info("Auction enrichment dry-run worker started")
    async with AsyncSessionLocal() as session:
        result = await dry_run_lot_enrichment_candidates(
            session,
            limit=DEFAULT_ENRICHMENT_CANDIDATE_LIMIT,
        )
    logger.info("Auction enrichment dry-run completed: %s", result.model_dump(mode="json"))
    return result.model_dump(mode="json")


def main() -> None:
    logging.basicConfig(level=settings.debug_level)
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("Auction enrichment dry-run worker stopped by interrupt")


if __name__ == "__main__":
    main()
