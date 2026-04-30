from __future__ import annotations

import asyncio
import json
import logging
from typing import TypeVar

from sqlalchemy import or_, select

from app.core.config import get_settings
from app.infrastructure.db.database import AsyncSessionLocal
from app.infrastructure.redis.streams import publish_auction_event
from app.models.auction import AuctionLotDetailCache, AuctionLotRecord, AuctionLotWorkItem
from app.services.auction_analysis_config import auction_analysis_config_service
from app.services.auction_datagrid_payload import validate_datagrid_row_payload
from app.services.auction_scoring import (
    SCORING_VERSION,
    build_record_score_input_hash,
    recalculate_record_rating,
    record_score_is_current,
)
from app.services.auction_sources import SOURCE_PROVIDERS


logger = logging.getLogger(__name__)
settings = get_settings()
_T = TypeVar("_T")


async def analyze_all_lots(limit: int | None = None) -> dict[str, int]:
    active_sources = tuple(SOURCE_PROVIDERS)
    if not active_sources:
        return _empty_metrics()

    async with AsyncSessionLocal() as session:
        statement = (
            select(AuctionLotRecord.id)
            .where(AuctionLotRecord.source_code.in_(active_sources))
            .where(
                or_(
                    AuctionLotRecord.scoring_version != SCORING_VERSION,
                    AuctionLotRecord.score_input_hash.is_(None),
                )
            )
            .order_by(AuctionLotRecord.scored_at.asc(), AuctionLotRecord.updated_at.desc(), AuctionLotRecord.id.asc())
        )
        if limit and limit > 0:
            statement = statement.limit(limit)
        record_ids = list((await session.scalars(statement)).all())
        if not record_ids:
            return _empty_metrics()
        runtime_config = await auction_analysis_config_service.get_runtime_config(session)

    metrics = _empty_metrics()
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
                metrics["processed"] += 1
                detail_cache = detail_caches.get(record.id)
                work_item = work_items.get(record.id)
                try:
                    input_hash = build_record_score_input_hash(
                        record,
                        detail_cache,
                        work_item,
                        category_keywords=runtime_config.category_keywords,
                        exclusion_keywords=runtime_config.exclusion_keywords,
                        legal_risk_rules=runtime_config.legal_risk_rules,
                        owner_profile=runtime_config.owner_profile,
                        dimension_weights=runtime_config.dimension_weights,
                    )
                    if record_score_is_current(record, input_hash=input_hash):
                        metrics["skipped_current"] += 1
                        continue

                    before = _visible_score_payload(record.datagrid_row)
                    recalculate_record_rating(
                        record,
                        detail_cache,
                        work_item,
                        category_keywords=runtime_config.category_keywords,
                        exclusion_keywords=runtime_config.exclusion_keywords,
                        legal_risk_rules=runtime_config.legal_risk_rules,
                        owner_profile=runtime_config.owner_profile,
                        dimension_weights=runtime_config.dimension_weights,
                    )
                    after = _visible_score_payload(record.datagrid_row)
                    if after == before:
                        metrics["unchanged"] += 1
                        continue
                    metrics["changed"] += 1
                    changed_rows.append(validate_datagrid_row_payload(record.datagrid_row).model_dump(mode="json"))
                except Exception:
                    metrics["failed"] += 1
                    logger.exception("Failed to recalculate auction lot score", extra={"lot_record_id": record.id})

            await session.commit()

        for row_chunk in _chunks(changed_rows, event_chunk_size):
            await publish_auction_event("lot.rows_updated", {"rows": row_chunk})
            if settings.auction_analysis_event_pause_seconds > 0:
                await asyncio.sleep(settings.auction_analysis_event_pause_seconds)
        await asyncio.sleep(0)

    metrics["updated"] = metrics["changed"]
    logger.info("Auction stale-score analysis metrics: %s", metrics)
    return metrics


def _empty_metrics() -> dict[str, int]:
    return {
        "processed": 0,
        "changed": 0,
        "updated": 0,
        "unchanged": 0,
        "skipped_current": 0,
        "failed": 0,
    }


def _visible_score_payload(datagrid_row: dict | None) -> str:
    row = datagrid_row or {}
    payload = {
        "rating": row.get("rating"),
        "analysis": row.get("analysis"),
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def _chunks(items: list[_T], size: int) -> list[list[_T]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


async def run_worker() -> None:
    logger.info("Auction analysis worker started")
    try:
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
    except asyncio.CancelledError:
        logger.info("Auction analysis worker shutdown requested")
        raise


def main() -> None:
    logging.basicConfig(level=settings.debug_level)
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("Auction analysis worker stopped by interrupt")


if __name__ == "__main__":
    main()
