from __future__ import annotations

import asyncio
import logging

from app.core.config import get_settings
from app.infrastructure.db.database import AsyncSessionLocal
from app.services.grid_side_effects import (
    GridSideEffectBatchResult,
    reset_stale_grid_side_effect_tasks,
    run_grid_side_effect_batch,
)
from app.worker.safety import safe_worker_sleep_seconds


logger = logging.getLogger(__name__)
settings = get_settings()


async def run_side_effect_batch() -> dict[str, int]:
    async with AsyncSessionLocal() as session:
        reset_count = await reset_stale_grid_side_effect_tasks(session)
        result = await run_grid_side_effect_batch(
            session,
            limit=settings.grid_side_effect_worker_batch_size,
            claim_ttl_seconds=settings.grid_side_effect_worker_claim_ttl_seconds,
            max_attempts=settings.grid_side_effect_worker_max_attempts,
            base_backoff_seconds=settings.grid_side_effect_worker_base_backoff_seconds,
        )
    payload = _result_payload(result, reset_count=reset_count)
    logger.info("Grid side effect batch completed: %s", payload)
    return payload


async def run_worker(*, run_once: bool = False) -> dict[str, int] | None:
    logger.info("Grid side effect worker started")
    try:
        while True:
            if not settings.grid_side_effect_worker_enabled:
                if run_once:
                    return None
                await asyncio.sleep(safe_worker_sleep_seconds(settings.grid_side_effect_worker_poll_interval_seconds))
                continue

            result = await run_side_effect_batch()
            if run_once:
                return result
            await asyncio.sleep(safe_worker_sleep_seconds(settings.grid_side_effect_worker_poll_interval_seconds))
    except asyncio.CancelledError:
        logger.info("Grid side effect worker shutdown requested")
        raise


def _result_payload(result: GridSideEffectBatchResult, *, reset_count: int) -> dict[str, int]:
    return {
        "selected": result.selected,
        "processed": result.processed,
        "failed": result.failed,
        "retried": result.retried,
        "reset": reset_count,
    }


def main() -> None:
    logging.basicConfig(level=settings.debug_level)
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("Grid side effect worker stopped by interrupt")


if __name__ == "__main__":
    main()
