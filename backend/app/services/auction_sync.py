from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.auction import (
    AuctionLotDetailCache,
    AuctionLotObservation,
    AuctionLotRecord,
    AuctionLotWorkItem,
    AuctionSourceState,
)
from app.schemas.auctions import AuctionListItem, SourceSyncResult
from app.services.auction_analysis_config import auction_analysis_config_service
from app.services.auction_catalog import build_datagrid_row
from app.services.auction_grid_state import bump_auction_lot_dataset_version
from app.services.auction_sources import get_source_provider
from app.services.lot_enrichment import (
    classify_lot_enrichment,
    evaluate_lot_ttl_refresh,
    schedule_lot_enrichment,
    schedule_lot_ttl_refresh,
)
from app.services.auction_scoring import recalculate_record_rating
from app.services.auction_scoring_invalidation import SOURCE_CONTENT_CHANGED
from app.services.auction_scoring import invalidate_lot_score
from app.services.auction_search import update_record_search_text
from app.services.auction_workspace import ensure_lot_detail_cache, ensure_work_item
from app.services.lot_decision_report import generate_and_persist_lot_decision_report_snapshot


settings = get_settings()
logger = logging.getLogger(__name__)
NEWNESS_WINDOW_DAYS = 3
SCRAPED_DATETIME_FORMATS = ("%d.%m.%Y %H:%M", "%d.%m.%Y", "%d/%m/%Y %H:%M", "%d/%m/%Y")


@dataclass(slots=True)
class PreparedLotSnapshot:
    item: AuctionListItem
    datagrid_row: dict
    normalized_item: dict
    content_hash: str
async def sync_source_lots(
    session: AsyncSession,
    *,
    source: str,
    limit: int = 100,
    on_progress: Callable[[dict], Awaitable[None]] | None = None,
) -> SourceSyncResult:
    provider = get_source_provider(source)
    source_info = provider.info()
    now = datetime.now(UTC)
    runtime_config = await auction_analysis_config_service.get_runtime_config(session)
    commit_chunk_size = max(1, settings.auction_sync_commit_chunk_size)
    progress_log_every = max(1, settings.auction_sync_progress_log_every)

    source_state = await session.get(AuctionSourceState, source_info.code)
    if source_state is None:
        source_state = AuctionSourceState(
            code=source_info.code,
            title=source_info.title,
            website=source_info.website,
            enabled=source_info.enabled,
        )
        session.add(source_state)
    else:
        source_state.title = source_info.title
        source_state.website = source_info.website
        source_state.enabled = source_info.enabled
    source_state.last_synced_at = now
    sync_start_page = _source_sync_start_page(source_info.code, source_state)

    result = SourceSyncResult(
        source=source_info.code,
        fetched=0,
        created=0,
        updated=0,
        unchanged=0,
        status_changed=0,
    )
    detail_sync_count = 0
    processed_items = 0

    if hasattr(provider, "iter_lots"):
        items_iterable = provider.iter_lots(limit, page=sync_start_page)
    else:
        items_iterable = await asyncio.to_thread(provider.list_lots, limit, page=sync_start_page)

    for source_position, item in enumerate(items_iterable, start=1):
        if not item.auction.external_id or not item.lot.external_id:
            continue

        result.fetched += 1
        processed_items += 1

        snapshot = _prepare_snapshot(item, source_info.title)
        snapshot.datagrid_row["source_position"] = source_position
        snapshot.normalized_item["source_position"] = source_position
        publication_at = _publication_datetime_from_item(item)
        record = await _find_lot_record(
            session,
            source_code=source_info.code,
            auction_external_id=item.auction.external_id,
            lot_external_id=item.lot.external_id,
        )

        if record is None:
            is_new = _is_new_record(published_at=publication_at, observed_at=now)
            record = AuctionLotRecord(
                source_code=source_info.code,
                auction_external_id=item.auction.external_id,
                lot_external_id=item.lot.external_id,
                auction_number=item.auction.number,
                lot_number=item.lot.number,
                lot_name=item.lot.name,
                status=item.lot.status,
                initial_price=item.lot.initial_price,
                content_hash=snapshot.content_hash,
                first_seen_at=now,
                last_seen_at=now,
                is_new=is_new,
                rating_score=snapshot.datagrid_row["rating"]["score"],
                rating_level=snapshot.datagrid_row["rating"]["level"],
                scoring_version=_rating_scoring_version(snapshot.datagrid_row),
                scored_at=_rating_scored_at(snapshot.datagrid_row),
                score_input_hash=_rating_input_hash(snapshot.datagrid_row),
                score_breakdown=_rating_breakdown(snapshot.datagrid_row),
                datagrid_row=_with_freshness(
                    snapshot.datagrid_row,
                    first_seen_at=now,
                    last_seen_at=now,
                    is_new=is_new,
                    published_at=publication_at,
                ),
                normalized_item=snapshot.normalized_item,
            )
            update_record_search_text(record)
            session.add(record)
            await session.flush()
            evaluation = classify_lot_enrichment(record)
            if evaluation.needs_enrichment:
                schedule_lot_enrichment(record, evaluation, requested_at=now, force=True)
            await _recalculate_record_with_cached_inputs(session, record, runtime_config=runtime_config)
            result.created += 1
            await _add_observation(session, record, snapshot)
            detail_sync_count = await _sync_detail_if_needed(
                session,
                record,
                detail_sync_count=detail_sync_count,
                refresh=True,
                observed_at=now,
                runtime_config=runtime_config,
            )
            await bump_auction_lot_dataset_version(
                session,
                record,
                event_type="row_inserted",
                payload={"source": "sync", "source_code": source_info.code, "changed_fields": ["row"]},
            )
        else:
            _preserve_existing_real_media(record, snapshot)
            publication_at = publication_at or _publication_datetime_from_row(record.datagrid_row)

            status_changed = record.status != item.lot.status
            content_changed = record.content_hash != snapshot.content_hash
            status_changed_at = now if status_changed else record.status_changed_at
            record.is_new = _is_new_record(published_at=publication_at, observed_at=now)
            next_row = _with_freshness(
                snapshot.datagrid_row,
                first_seen_at=record.first_seen_at,
                last_seen_at=now,
                status_changed_at=status_changed_at,
                is_new=record.is_new,
                published_at=publication_at,
            )
            preserved_scoring = _record_scoring_payload(record) if content_changed else None
            if preserved_scoring is not None:
                next_row["rating"] = preserved_scoring["rating"]

            record.last_seen_at = now
            record.auction_number = item.auction.number
            record.lot_number = item.lot.number
            record.lot_name = item.lot.name
            record.status = item.lot.status
            record.initial_price = item.lot.initial_price
            record.datagrid_row = next_row
            record.normalized_item = snapshot.normalized_item
            update_record_search_text(record)
            if content_changed:
                invalidate_lot_score(record, reason=SOURCE_CONTENT_CHANGED)
                evaluation = classify_lot_enrichment(record)
                if evaluation.needs_enrichment or record.enrichment_requested_at is not None:
                    schedule_lot_enrichment(record, evaluation, requested_at=now, force=True)
            else:
                record.rating_score = snapshot.datagrid_row["rating"]["score"]
                record.rating_level = snapshot.datagrid_row["rating"]["level"]
                record.scoring_version = _rating_scoring_version(snapshot.datagrid_row)
                record.scored_at = _rating_scored_at(snapshot.datagrid_row)
                record.score_input_hash = _rating_input_hash(snapshot.datagrid_row)
                record.score_breakdown = _rating_breakdown(snapshot.datagrid_row)

            if preserved_scoring is not None:
                _apply_record_scoring(record, preserved_scoring)
                record.score_input_hash = None

            if status_changed:
                record.status_changed_at = now
                result.status_changed += 1
            if content_changed or status_changed:
                record.content_hash = snapshot.content_hash
                await _recalculate_record_with_cached_inputs(session, record, runtime_config=runtime_config)
            if content_changed:
                result.updated += 1
                await _add_observation(session, record, snapshot)
                detail_sync_count = await _sync_detail_if_needed(
                    session,
                    record,
                    detail_sync_count=detail_sync_count,
                    refresh=True,
                    observed_at=now,
                    runtime_config=runtime_config,
                )
            else:
                result.unchanged += 1
                detail_sync_count = await _sync_detail_if_needed(
                    session,
                    record,
                    detail_sync_count=detail_sync_count,
                    refresh=False,
                    observed_at=now,
                    runtime_config=runtime_config,
                )
            if content_changed or status_changed:
                changed_fields = []
                if content_changed:
                    changed_fields.append("content")
                if status_changed:
                    changed_fields.append("status")
                await bump_auction_lot_dataset_version(
                    session,
                    record,
                    event_type="row_updated",
                    payload={"source": "sync", "source_code": source_info.code, "changed_fields": changed_fields},
                )

        if processed_items % progress_log_every == 0:
            logger.info(
                "Sync progress for %s: %s/%s processed, created=%s, updated=%s, unchanged=%s, details=%s",
                source_info.code,
                processed_items,
                result.fetched,
                result.created,
                result.updated,
                result.unchanged,
                detail_sync_count,
            )

        if processed_items % commit_chunk_size == 0:
            await session.commit()
            logger.info(
                "Sync chunk committed for %s: %s/%s processed",
                source_info.code,
                processed_items,
                result.fetched,
            )
            if on_progress is not None:
                await on_progress(
                    {
                        **result.model_dump(mode="json"),
                        "processed": processed_items,
                        "details_synced": detail_sync_count,
                    }
                )

    await session.commit()
    _advance_source_sync_cursor(source_info.code, source_state, start_page=sync_start_page, fetched=result.fetched)
    await _backfill_publication_dates(session, source_code=source_info.code, observed_at=now)
    await session.commit()
    logger.info(
        "Sync finished for %s: fetched=%s, created=%s, updated=%s, unchanged=%s, status_changed=%s, details=%s",
        source_info.code,
        result.fetched,
        result.created,
        result.updated,
        result.unchanged,
        result.status_changed,
        detail_sync_count,
    )
    return result


def _source_sync_start_page(source_code: str, source_state: AuctionSourceState) -> int:
    if source_code != "tbankrot" or not settings.tbankrot_page_rotation_enabled:
        return 1
    cursor = source_state.sync_cursor if isinstance(source_state.sync_cursor, dict) else {}
    next_page = cursor.get("next_page")
    return max(1, int(next_page)) if isinstance(next_page, int | str) and str(next_page).isdigit() else 1


def _advance_source_sync_cursor(
    source_code: str,
    source_state: AuctionSourceState,
    *,
    start_page: int,
    fetched: int,
) -> None:
    if source_code != "tbankrot" or not settings.tbankrot_page_rotation_enabled:
        return

    window_size = max(1, settings.tbankrot_pages)
    max_page = max(0, settings.tbankrot_page_rotation_max_page)
    if fetched <= 0:
        next_page = 1
    else:
        next_page = start_page + window_size
        if max_page > 0 and next_page > max_page:
            next_page = 1

    cursor = dict(source_state.sync_cursor or {})
    cursor["next_page"] = next_page
    cursor["last_start_page"] = start_page
    cursor["last_window_size"] = window_size
    cursor["last_fetched"] = fetched
    source_state.sync_cursor = cursor


async def _sync_detail_if_needed(
    session: AsyncSession,
    record: AuctionLotRecord,
    *,
    detail_sync_count: int,
    refresh: bool,
    observed_at: datetime,
    runtime_config: object,
) -> int:
    if not settings.auction_detail_sync_enabled:
        return detail_sync_count
    if detail_sync_count >= settings.auction_detail_sync_limit:
        return detail_sync_count

    try:
        detail_cache = await ensure_lot_detail_cache(
            session,
            record,
            refresh=refresh,
            include_price_schedule=False,
        )
    except NotImplementedError:
        logger.info("Detail sync is not implemented for source %s", record.source_code)
        return detail_sync_count
    _apply_record_freshness(record, observed_at=observed_at, published_at=_publication_datetime_from_detail_cache(detail_cache))
    work_item = await ensure_work_item(session, record)
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
    update_record_search_text(record)
    await generate_and_persist_lot_decision_report_snapshot(session, record, detail_cache, work_item)
    ttl_evaluation = evaluate_lot_ttl_refresh(record, detail_cache, current_time=observed_at)
    schedule_lot_ttl_refresh(record, ttl_evaluation, requested_at=observed_at)
    return detail_sync_count + 1


async def _recalculate_record_with_cached_inputs(
    session: AsyncSession,
    record: AuctionLotRecord,
    *,
    runtime_config: object,
) -> None:
    detail_cache = await session.scalar(select(AuctionLotDetailCache).where(AuctionLotDetailCache.lot_record_id == record.id))
    work_item = await session.scalar(select(AuctionLotWorkItem).where(AuctionLotWorkItem.lot_record_id == record.id))
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
    update_record_search_text(record)
    await generate_and_persist_lot_decision_report_snapshot(session, record, detail_cache, work_item)


async def _find_lot_record(
    session: AsyncSession,
    *,
    source_code: str,
    auction_external_id: str,
    lot_external_id: str,
) -> AuctionLotRecord | None:
    statement = select(AuctionLotRecord).where(
        AuctionLotRecord.source_code == source_code,
        AuctionLotRecord.auction_external_id == auction_external_id,
        AuctionLotRecord.lot_external_id == lot_external_id,
    )
    return await session.scalar(statement)


async def _add_observation(session: AsyncSession, record: AuctionLotRecord, snapshot: PreparedLotSnapshot) -> None:
    session.add(
        AuctionLotObservation(
            lot_record_id=record.id,
            content_hash=snapshot.content_hash,
            status=record.status,
            datagrid_row=record.datagrid_row,
            normalized_item=snapshot.normalized_item,
        )
    )


def _prepare_snapshot(item: AuctionListItem, source_title: str) -> PreparedLotSnapshot:
    datagrid_row = build_datagrid_row(item, source_title).model_dump(mode="json")
    normalized_item = item.model_dump(mode="json")
    content_lot = dict(normalized_item["lot"])
    content_lot.pop("price_schedule", None)
    content_payload = {
        "auction": normalized_item["auction"],
        "lot": content_lot,
        "organizer": normalized_item["organizer"],
        "winner": normalized_item.get("winner"),
    }
    content_hash = hashlib.sha256(
        json.dumps(content_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return PreparedLotSnapshot(
        item=item,
        datagrid_row=datagrid_row,
        normalized_item=normalized_item,
        content_hash=content_hash,
    )


def _preserve_existing_real_media(record: AuctionLotRecord, snapshot: PreparedLotSnapshot) -> None:
    existing_images = _media_images_from_row(record.datagrid_row)
    if not _has_real_media(existing_images):
        return

    next_images = _media_images_from_row(snapshot.datagrid_row)
    if _has_real_media(next_images):
        return

    primary_url = _first_real_media_url(existing_images) or _string_value((record.datagrid_row or {}).get("primary_image_url"))
    snapshot.datagrid_row["images"] = existing_images
    snapshot.datagrid_row["primary_image_url"] = primary_url
    snapshot.datagrid_row["image_count"] = len(existing_images)

    normalized_item = dict(snapshot.normalized_item or {})
    lot_payload = dict(normalized_item.get("lot") or {})
    lot_payload["images"] = existing_images
    lot_payload["primary_image_url"] = primary_url
    normalized_item["lot"] = lot_payload
    snapshot.normalized_item = normalized_item


def _media_images_from_row(row: dict | None) -> list[dict]:
    if not isinstance(row, dict):
        return []
    images = row.get("images")
    return [dict(image) for image in images if isinstance(image, dict)] if isinstance(images, list) else []


def _has_real_media(images: list[dict]) -> bool:
    return any(_is_real_media_url(_string_value(image.get("url"))) for image in images)


def _first_real_media_url(images: list[dict]) -> str | None:
    for image in images:
        url = _string_value(image.get("url"))
        if _is_real_media_url(url):
            return url
    return None


def _is_real_media_url(url: str | None) -> bool:
    if not url:
        return False
    lowered = url.lower()
    return not ("/img/blur/" in lowered or "/blur_" in lowered)


def _string_value(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _rating_payload(row: dict) -> dict:
    rating = row.get("rating")
    return rating if isinstance(rating, dict) else {}


def _rating_scoring_version(row: dict) -> str:
    value = _rating_payload(row).get("scoring_version")
    return value if isinstance(value, str) and value else "unscored"


def _rating_input_hash(row: dict) -> str | None:
    value = _rating_payload(row).get("input_hash")
    return value if isinstance(value, str) and value else None


def _rating_breakdown(row: dict) -> dict:
    value = _rating_payload(row).get("breakdown")
    return value if isinstance(value, dict) else {}


def _rating_scored_at(row: dict) -> datetime | None:
    value = _rating_payload(row).get("scored_at")
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _record_scoring_payload(record: AuctionLotRecord) -> dict:
    return {
        "rating_score": record.rating_score,
        "rating_level": record.rating_level,
        "scoring_version": record.scoring_version,
        "scored_at": record.scored_at,
        "score_input_hash": record.score_input_hash,
        "score_breakdown": record.score_breakdown,
        "rating": _rating_payload(record.datagrid_row),
    }


def _apply_record_scoring(record: AuctionLotRecord, payload: dict) -> None:
    record.rating_score = payload["rating_score"]
    record.rating_level = payload["rating_level"]
    record.scoring_version = payload["scoring_version"]
    record.scored_at = payload["scored_at"]
    record.score_input_hash = payload["score_input_hash"]
    record.score_breakdown = payload["score_breakdown"]


def _with_freshness(
    row: dict,
    *,
    first_seen_at: datetime,
    last_seen_at: datetime,
    is_new: bool,
    published_at: datetime | None = None,
    status_changed_at: datetime | None = None,
) -> dict:
    updated_row = dict(row)
    if published_at:
        updated_row["publication_date"] = _format_publication_date(published_at)
    updated_row["freshness"] = {
        "is_new": is_new,
        "published_at": published_at.isoformat() if published_at else None,
        "first_seen_at": first_seen_at.isoformat(),
        "last_seen_at": last_seen_at.isoformat(),
        "status_changed_at": status_changed_at.isoformat() if status_changed_at else None,
    }
    return updated_row


def _is_new_record(*, published_at: datetime | None, observed_at: datetime) -> bool:
    if published_at is None:
        return False
    return observed_at - published_at <= timedelta(days=NEWNESS_WINDOW_DAYS)


def _publication_datetime_from_item(item: AuctionListItem) -> datetime | None:
    return _parse_scraped_datetime(item.auction.publication_date)


def _publication_datetime_from_detail_cache(detail_cache) -> datetime | None:
    if detail_cache is None:
        return None
    for payload in (detail_cache.auction_detail or {}, detail_cache.lot_detail or {}):
        auction = payload.get("auction") or {}
        parsed = _parse_scraped_datetime(auction.get("publication_date"))
        if parsed:
            return parsed
    return None


def _publication_datetime_from_row(row: dict | None) -> datetime | None:
    if not row:
        return None
    freshness = row.get("freshness") or {}
    return _parse_scraped_datetime(freshness.get("published_at") or row.get("publication_date"))


def _parse_scraped_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip()
    try:
        parsed_iso = datetime.fromisoformat(normalized)
        return parsed_iso if parsed_iso.tzinfo else parsed_iso.replace(tzinfo=UTC)
    except ValueError:
        pass
    for fmt in SCRAPED_DATETIME_FORMATS:
        try:
            return datetime.strptime(normalized, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _apply_record_freshness(record: AuctionLotRecord, *, observed_at: datetime, published_at: datetime | None) -> None:
    published_at = published_at or _publication_datetime_from_row(record.datagrid_row)
    record.is_new = _is_new_record(published_at=published_at, observed_at=observed_at)
    record.datagrid_row = _with_freshness(
        record.datagrid_row,
        first_seen_at=record.first_seen_at,
        last_seen_at=record.last_seen_at,
        is_new=record.is_new,
        published_at=published_at,
        status_changed_at=record.status_changed_at,
    )
    update_record_search_text(record)


def _format_publication_date(value: datetime) -> str:
    if value.hour == 0 and value.minute == 0 and value.second == 0:
        return value.strftime("%d.%m.%Y")
    return value.strftime("%d.%m.%Y %H:%M")


async def _backfill_publication_dates(
    session: AsyncSession,
    *,
    source_code: str,
    observed_at: datetime,
) -> None:
    max_publication_fetches = settings.auction_publication_sync_limit
    if max_publication_fetches <= 0:
        return

    provider = get_source_provider(source_code)
    statement = (
        select(AuctionLotRecord)
        .where(AuctionLotRecord.source_code == source_code)
        .order_by(AuctionLotRecord.last_seen_at.desc())
        .limit(max_publication_fetches)
    )
    records = (await session.scalars(statement)).all()
    if not records:
        return

    record_ids = [record.id for record in records]
    detail_caches = {
        detail_cache.lot_record_id: detail_cache
        for detail_cache in (
            await session.scalars(
                select(AuctionLotDetailCache).where(AuctionLotDetailCache.lot_record_id.in_(record_ids))
            )
        ).all()
    }

    auction_ids_to_fetch: list[str] = []
    seen_auction_ids: set[str] = set()
    for record in records:
        auction_id = record.auction_external_id
        if not auction_id or auction_id in seen_auction_ids:
            continue
        seen_auction_ids.add(auction_id)
        detail_cache = detail_caches.get(record.id)
        existing_publication_at = _publication_datetime_from_row(record.datagrid_row) or _publication_datetime_from_detail_cache(detail_cache)
        if existing_publication_at is not None:
            row = dict(record.datagrid_row or {})
            if not row.get("publication_date"):
                row["publication_date"] = _format_publication_date(existing_publication_at)
                record.datagrid_row = row
                _apply_record_freshness(record, observed_at=observed_at, published_at=existing_publication_at)
                await bump_auction_lot_dataset_version(
                    session,
                    record,
                    event_type="row_updated",
                    payload={
                        "source": "sync_publication_backfill",
                        "source_code": source_code,
                        "changed_fields": ["publication_date", "freshness"],
                    },
                )
            normalized_item = dict(record.normalized_item or {})
            auction_payload = dict(normalized_item.get("auction") or {})
            if not auction_payload.get("publication_date"):
                auction_payload["publication_date"] = _format_publication_date(existing_publication_at)
                normalized_item["auction"] = auction_payload
                record.normalized_item = normalized_item
            continue
        auction_ids_to_fetch.append(auction_id)
        if len(auction_ids_to_fetch) >= max_publication_fetches:
            break

    if not auction_ids_to_fetch:
        return

    semaphore = asyncio.Semaphore(4)

    async def fetch_publication(auction_id: str) -> tuple[str, str | None, datetime | None]:
        async with semaphore:
            try:
                publication_date = await asyncio.to_thread(provider.get_auction_publication_date, auction_id)
            except Exception:
                return auction_id, None, None
            return auction_id, publication_date, _parse_scraped_datetime(publication_date)

    publication_results = await asyncio.gather(*(fetch_publication(auction_id) for auction_id in auction_ids_to_fetch))
    publication_by_auction = {
        auction_id: (publication_date, published_at)
        for auction_id, publication_date, published_at in publication_results
        if publication_date and published_at
    }
    if not publication_by_auction:
        return

    affected_records = (
        await session.scalars(
            select(AuctionLotRecord).where(
                AuctionLotRecord.source_code == source_code,
                AuctionLotRecord.auction_external_id.in_(list(publication_by_auction)),
            )
        )
    ).all()

    for record in affected_records:
        publication_date, published_at = publication_by_auction[record.auction_external_id]
        row = dict(record.datagrid_row or {})
        row["publication_date"] = publication_date
        record.datagrid_row = row
        normalized_item = dict(record.normalized_item or {})
        auction_payload = dict(normalized_item.get("auction") or {})
        auction_payload["publication_date"] = publication_date
        normalized_item["auction"] = auction_payload
        record.normalized_item = normalized_item
        _apply_record_freshness(record, observed_at=observed_at, published_at=published_at)
        await bump_auction_lot_dataset_version(
            session,
            record,
            event_type="row_updated",
            payload={
                "source": "sync_publication_backfill",
                "source_code": source_code,
                "changed_fields": ["publication_date", "freshness"],
            },
        )
