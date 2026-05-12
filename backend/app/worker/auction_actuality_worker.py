from __future__ import annotations

import asyncio
import logging

from app.core.config import get_settings
from app.infrastructure.db.database import AsyncSessionLocal
from app.services.lot_actuality import run_lot_actuality_sweep
from app.worker.safety import safe_worker_sleep_seconds


logger = logging.getLogger(__name__)
settings = get_settings()


def calculate_actuality_sweep_worker_delay(interval_seconds: int | float | None = None) -> float:
    configured_interval = (
        settings.auction_actuality_sweep_interval_seconds if interval_seconds is None else interval_seconds
    )
    return safe_worker_sleep_seconds(configured_interval)


async def run_actuality_sweep_batch() -> dict[str, object]:
    async with AsyncSessionLocal() as session:
        result = await run_lot_actuality_sweep(
            session,
            limit=settings.auction_actuality_sweep_batch_size,
        )
        await session.commit()
    payload = result.model_dump(mode="json")
    logger.info("Auction actuality sweep completed: %s", payload)
    return payload


async def run_worker(*, run_once: bool = False) -> dict[str, object] | None:
    logger.info("Auction actuality worker started")
    try:
        while True:
            if not settings.auction_actuality_sweep_enabled:
                if run_once:
                    return None
                await asyncio.sleep(calculate_actuality_sweep_worker_delay())
                continue

            try:
                result = await run_actuality_sweep_batch()
            except Exception:
                logger.exception("Auction actuality sweep failed")
                if run_once:
                    raise
                await asyncio.sleep(calculate_actuality_sweep_worker_delay())
                continue

            if run_once:
                return result
            await asyncio.sleep(calculate_actuality_sweep_worker_delay())
    except asyncio.CancelledError:
        logger.info("Auction actuality worker shutdown requested")
        raise


def main() -> None:
    logging.basicConfig(level=settings.debug_level)
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("Auction actuality worker stopped by interrupt")


if __name__ == "__main__":
    main()
