from __future__ import annotations

import asyncio
import json
import logging
from typing import TypeVar

from sqlalchemy import select

from app.core.config import get_settings
from app.infrastructure.db.database import AsyncSessionLocal
from app.infrastructure.redis.streams import publish_auction_event
from app.models.auction import AuctionLotDetailCache, AuctionLotRecord, AuctionLotWorkItem
from app.schemas.auctions import LotDatagridRow
from app.services.auction_analysis_config import auction_analysis_config_service
from app.services.auction_sources import SOURCE_PROVIDERS
from app.services.auction_workspace import recalculate_record_rating


logger = logging.getLogger(__name__)
settings = get_settings()
_T = TypeVar("_T")


async def analyze_all_lots(limit: int | None = None) -> dict[str, int]:
    active_sources = tuple(SOURCE_PROVIDERS)
    if not active_sources:
        return {"processed": 0, "updated": 0, "unchanged": 0}

    async with AsyncSessionLocal() as session:
        statement = (
            select(AuctionLotRecord.id)
            .where(AuctionLotRecord.source_code.in_(active_sources))
            .order_by(AuctionLotRecord.updated_at.asc(), AuctionLotRecord.id.asc())
        )
        if limit and limit > 0:
            statement = statement.limit(limit)
        record_ids = list((await session.scalars(statement)).all())
        if not record_ids:
            return {"processed": 0, "updated": 0, "unchanged": 0}
        runtime_config = await auction_analysis_config_service.get_runtime_config(session)

    processed = 0
    updated = 0
    chunk_size = max(1, settings.auction_analysis_commit_chunk_size)
    event_chunk_size = max(1, settings.auction_analysis_event_chunk_size)

    for chunk_ids in _chunks(record_ids, chunk_size):
        async with AsyncSessionLocal() as session:
            records_by_id = {
                record.id: record
                for record in (await session.scalars(select(AuctionLotRecord).where(AuctionLotRecord.id.in_(chunk_ids)))).all()
            }
            records = [records_by_id[record_id] for record_id in chunk_ids if record_id in records_by_id]
            if not records:
                continue

            detail_caches = {
                cache.lot_record_id: cache
                for cache in (
                    await session.scalars(
                        select(AuctionLotDetailCache).where(AuctionLotDetailCache.lot_record_id.in_(chunk_ids))
                    )
                ).all()
            }
            work_items = {
                work_item.lot_record_id: work_item
                for work_item in (
                    await session.scalars(select(AuctionLotWorkItem).where(AuctionLotWorkItem.lot_record_id.in_(chunk_ids)))
                ).all()
            }

            changed_rows: list[dict] = []
            for record in records:
                before = json.dumps(record.datagrid_row, sort_keys=True, ensure_ascii=False)
                recalculate_record_rating(
                    record,
                    detail_caches.get(record.id),
                    work_items.get(record.id),
                    category_keywords=runtime_config.category_keywords,
                    exclusion_keywords=runtime_config.exclusion_keywords,
                    legal_risk_rules=runtime_config.legal_risk_rules,
                )
                after = json.dumps(record.datagrid_row, sort_keys=True, ensure_ascii=False)
                if after == before:
                    continue
                changed_rows.append(LotDatagridRow.model_validate(record.datagrid_row).model_dump(mode="json"))

            await session.commit()

        processed += len(chunk_ids)
        updated += len(changed_rows)
        for row_chunk in _chunks(changed_rows, event_chunk_size):
            await publish_auction_event("lot.rows_updated", {"rows": row_chunk})
            if settings.auction_analysis_event_pause_seconds > 0:
                await asyncio.sleep(settings.auction_analysis_event_pause_seconds)
        await asyncio.sleep(0)

    return {
        "processed": processed,
        "updated": updated,
        "unchanged": processed - updated,
    }


def _chunks(items: list[_T], size: int) -> list[list[_T]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


async def run_worker() -> None:
    logger.info("Auction analysis worker started")
    while True:
        if not settings.auction_analysis_enabled:
            await asyncio.sleep(settings.auction_analysis_interval_seconds)
            continue

        await publish_auction_event("analysis.started", {})
        try:
            result = await analyze_all_lots(limit=settings.auction_analysis_batch_size)
            await publish_auction_event("analysis.completed", result)
            logger.info("Auction analysis completed: %s", result)
        except Exception as error:
            logger.exception("Auction analysis failed")
            await publish_auction_event("analysis.failed", {"error": str(error)})

        await asyncio.sleep(settings.auction_analysis_interval_seconds)


def main() -> None:
    logging.basicConfig(level=settings.debug_level)
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
