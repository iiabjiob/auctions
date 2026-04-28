from __future__ import annotations

import asyncio
import json
import logging

from sqlalchemy import select

from app.core.config import get_settings
from app.infrastructure.db.database import AsyncSessionLocal
from app.infrastructure.redis.streams import publish_auction_event
from app.models.auction import AuctionLotDetailCache, AuctionLotRecord, AuctionLotWorkItem
from app.schemas.auctions import LotDatagridRow
from app.services.auction_analysis_config import auction_analysis_config_service
from app.services.auction_workspace import recalculate_record_rating


logger = logging.getLogger(__name__)
settings = get_settings()


async def analyze_all_lots(limit: int | None = None) -> dict[str, int]:
    async with AsyncSessionLocal() as session:
        statement = select(AuctionLotRecord).order_by(AuctionLotRecord.updated_at.asc(), AuctionLotRecord.id.asc())
        if limit and limit > 0:
            statement = statement.limit(limit)
        records = list((await session.scalars(statement)).all())
        if not records:
            return {"processed": 0, "updated": 0, "unchanged": 0}

        record_ids = [record.id for record in records]
        detail_caches = {
            cache.lot_record_id: cache
            for cache in (
                await session.scalars(
                    select(AuctionLotDetailCache).where(AuctionLotDetailCache.lot_record_id.in_(record_ids))
                )
            ).all()
        }
        work_items = {
            work_item.lot_record_id: work_item
            for work_item in (
                await session.scalars(select(AuctionLotWorkItem).where(AuctionLotWorkItem.lot_record_id.in_(record_ids)))
            ).all()
        }
        runtime_config = await auction_analysis_config_service.get_runtime_config(session)

        changed_rows: list[dict] = []
        updated = 0
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
            updated += 1
            changed_rows.append(LotDatagridRow.model_validate(record.datagrid_row).model_dump(mode="json"))

        await session.commit()

    for row in changed_rows:
        await publish_auction_event("lot.row_updated", {"row": row})

    return {
        "processed": len(records),
        "updated": updated,
        "unchanged": len(records) - updated,
    }


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