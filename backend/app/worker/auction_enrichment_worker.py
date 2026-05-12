from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.infrastructure.redis.streams import publish_auction_event
from app.models.auction import AuctionLotDetailCache, AuctionLotRecord
from app.infrastructure.db.database import AsyncSessionLocal
from app.services.lot_enrichment import (
    DEFAULT_ENRICHMENT_CANDIDATE_LIMIT,
    execute_lot_enrichment_candidates,
    schedule_priority_lot_enrichment,
)
from app.services.auction_datagrid_payload import validate_datagrid_row_payload
from app.worker.safety import safe_worker_sleep_seconds


logger = logging.getLogger(__name__)
settings = get_settings()


def calculate_enrichment_worker_delay(
    result: dict[str, object] | None = None,
    *,
    failure_count: int = 0,
    interval_seconds: int | float | None = None,
    empty_pause_seconds: int | float | None = None,
) -> float:
    configured_interval = settings.auction_enrichment_interval_seconds if interval_seconds is None else interval_seconds
    configured_empty_pause = (
        settings.auction_enrichment_empty_pause_seconds if empty_pause_seconds is None else empty_pause_seconds
    )
    base_delay = safe_worker_sleep_seconds(configured_interval)
    candidate_count = result.get("candidate_count") if result is not None else None
    if candidate_count == 0:
        base_delay = max(base_delay, safe_worker_sleep_seconds(configured_empty_pause))
    if failure_count <= 0:
        return base_delay
    return safe_worker_sleep_seconds(base_delay * (2 ** min(failure_count - 1, 8)))


async def run_enrichment_batch() -> dict[str, object]:
    async with AsyncSessionLocal() as session:
        await schedule_priority_lot_enrichment(session)
        result = await execute_lot_enrichment_candidates(
            session,
            limit=settings.auction_enrichment_batch_size or DEFAULT_ENRICHMENT_CANDIDATE_LIMIT,
            item_pause_seconds=max(0.0, settings.auction_enrichment_item_pause_seconds),
        )
        await session.commit()
        await _publish_enrichment_completion_events(session, result.completed_record_ids)
    logger.info("Auction enrichment completed: %s", result.model_dump(mode="json"))
    return result.model_dump(mode="json")


async def run_worker(*, run_once: bool = False) -> dict[str, object] | None:
    logger.info("Auction enrichment worker started")
    failure_count = 0
    try:
        while True:
            if not settings.auction_enrichment_enabled:
                if run_once:
                    return None
                await asyncio.sleep(calculate_enrichment_worker_delay())
                continue

            try:
                result = await run_enrichment_batch()
                failure_count = 0
            except Exception:
                failure_count += 1
                logger.exception("Auction enrichment batch failed")
                if run_once:
                    raise
                await asyncio.sleep(calculate_enrichment_worker_delay(failure_count=failure_count))
                continue
            if run_once:
                return result
            await asyncio.sleep(calculate_enrichment_worker_delay(result))
    except asyncio.CancelledError:
        logger.info("Auction enrichment worker shutdown requested")
        raise


def main() -> None:
    logging.basicConfig(level=settings.debug_level)
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("Auction enrichment worker stopped by interrupt")


async def _publish_enrichment_completion_events(session: AsyncSession, record_ids: list[int]) -> None:
    if not record_ids:
        return
    records = (await session.scalars(select(AuctionLotRecord).where(AuctionLotRecord.id.in_(record_ids)))).all()
    for record in records:
        row = validate_datagrid_row_payload(record.datagrid_row)
        await publish_auction_event("lot.row_updated", {"row": row.model_dump(mode="json")})
        detail_cache = await session.scalar(
            select(AuctionLotDetailCache).where(AuctionLotDetailCache.lot_record_id == record.id)
        )
        await publish_auction_event(
            "lot.detail_refresh_completed",
            {
                "source": record.source_code,
                "lot_id": record.lot_external_id,
                "auction_id": record.auction_external_id,
                "record_id": record.id,
                "detail_cached_at": detail_cache.fetched_at.isoformat() if detail_cache and detail_cache.fetched_at else None,
            },
        )


if __name__ == "__main__":
    main()
