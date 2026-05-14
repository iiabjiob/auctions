from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.infrastructure.db.database import AsyncSessionLocal
from app.models.procurement import ProcurementLotRecord
from app.services.procurement_enrichment import (
    DEFAULT_PROCUREMENT_ENRICHMENT_CANDIDATE_LIMIT,
    execute_procurement_enrichment_candidates,
)
from app.worker.safety import safe_worker_sleep_seconds


logger = logging.getLogger(__name__)
settings = get_settings()


def calculate_procurement_enrichment_worker_delay(
    result: dict[str, object] | None = None,
    *,
    failure_count: int = 0,
    interval_seconds: int | float | None = None,
    empty_pause_seconds: int | float | None = None,
) -> float:
    configured_interval = settings.procurement_enrichment_interval_seconds if interval_seconds is None else interval_seconds
    configured_empty_pause = (
        settings.procurement_enrichment_empty_pause_seconds
        if empty_pause_seconds is None
        else empty_pause_seconds
    )
    base_delay = safe_worker_sleep_seconds(configured_interval)
    if result is not None and result.get("candidate_count") == 0:
        base_delay = max(base_delay, safe_worker_sleep_seconds(configured_empty_pause))
    if failure_count <= 0:
        return base_delay
    return safe_worker_sleep_seconds(base_delay * (2 ** min(failure_count - 1, 8)))


async def run_enrichment_batch() -> dict[str, object]:
    async with AsyncSessionLocal() as session:
        result = await execute_procurement_enrichment_candidates(
            session,
            limit=settings.procurement_enrichment_batch_size or DEFAULT_PROCUREMENT_ENRICHMENT_CANDIDATE_LIMIT,
            item_pause_seconds=max(0.0, settings.procurement_enrichment_item_pause_seconds),
        )
        await session.commit()
        await _log_completed_records(session, result.completed_record_ids)
    payload = result.model_dump(mode="json")
    logger.info("Procurement enrichment completed: %s", payload)
    return payload


async def run_worker(*, run_once: bool = False) -> dict[str, object] | None:
    logger.info("Procurement enrichment worker started")
    failure_count = 0
    try:
        while True:
            if not settings.procurement_enrichment_enabled:
                if run_once:
                    return None
                await asyncio.sleep(calculate_procurement_enrichment_worker_delay())
                continue

            try:
                result = await run_enrichment_batch()
                failure_count = 0
            except Exception:
                failure_count += 1
                logger.exception("Procurement enrichment batch failed")
                if run_once:
                    raise
                await asyncio.sleep(calculate_procurement_enrichment_worker_delay(failure_count=failure_count))
                continue
            if run_once:
                return result
            await asyncio.sleep(calculate_procurement_enrichment_worker_delay(result))
    except asyncio.CancelledError:
        logger.info("Procurement enrichment worker shutdown requested")
        raise


async def _log_completed_records(session: AsyncSession, record_ids: list[int]) -> None:
    if not record_ids:
        return
    records = (await session.scalars(select(ProcurementLotRecord).where(ProcurementLotRecord.id.in_(record_ids)))).all()
    for record in records:
        logger.info(
            "Procurement lot enriched: source=%s external_id=%s record_id=%s",
            record.source_code,
            record.external_id,
            record.id,
        )


def main() -> None:
    logging.basicConfig(level=settings.debug_level)
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("Procurement enrichment worker stopped by interrupt")


if __name__ == "__main__":
    main()
