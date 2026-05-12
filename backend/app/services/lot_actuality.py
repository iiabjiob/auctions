from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import case, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, ConfigDict, Field

from app.models.auction import AuctionLotDetailCache, AuctionLotRecord
from app.services.auction_grid_state import bump_auction_lot_dataset_version


TERMINAL_LOT_STATUS_MARKERS: tuple[str, ...] = (
    "архив",
    "archived",
    "заверш",
    "закончен",
    "состоял",
    "состоялись",
    "подвед",
    "отмен",
)
DEFAULT_ACTUALITY_GRACE = timedelta(hours=24)
DEFAULT_STALE_AFTER = timedelta(days=30)
SCRAPED_DATETIME_FORMATS: tuple[str, ...] = (
    "%d.%m.%Y %H:%M:%S",
    "%d.%m.%Y %H:%M",
    "%d.%m.%Y",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
)
PUBLICATION_FIELD_ALIASES: tuple[str, ...] = ("publication_at", "publication_date", "published_at")
APPLICATION_START_FIELD_ALIASES: tuple[str, ...] = (
    "application_start_at",
    "application_start",
    "application_begin_at",
    "application_begin",
)
APPLICATION_DEADLINE_FIELD_ALIASES: tuple[str, ...] = (
    "application_deadline_at",
    "application_deadline",
    "application_end_at",
    "application_end",
)
AUCTION_FIELD_ALIASES: tuple[str, ...] = ("auction_at", "auction_date", "auction_start_at", "auction_start")
RAW_PUBLICATION_LABELS: tuple[str, ...] = ("публикац",)
RAW_APPLICATION_START_LABELS: tuple[str, ...] = ("прием заявок", "приём заявок", "представления заявок")
RAW_APPLICATION_DEADLINE_LABELS: tuple[str, ...] = ("прием заявок", "приём заявок", "окончания приема заявок", "окончания приёма заявок")
RAW_AUCTION_LABELS: tuple[str, ...] = ("проведение торгов", "дата проведения", "дата начала торгов", "начало торгов", "аукцион")


class LotActualityDates(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    publication_at: datetime | None = None
    application_start_at: datetime | None = None
    application_deadline_at: datetime | None = None
    auction_at: datetime | None = None


class LotActualityClassification(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    lifecycle_status: str
    finished_at: datetime | None = None
    archive_reason: str | None = None
    dates: LotActualityDates = Field(default_factory=LotActualityDates)


class LotActualitySweepResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_count: int
    processed_count: int
    updated_count: int
    active_to_non_active_count: int
    non_active_to_active_count: int
    skipped_count: int
    candidate_record_ids: list[int] = Field(default_factory=list)


def parse_lot_datetime(value: str | None) -> datetime | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized:
        return None

    iso_value = normalized.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(iso_value)
    except ValueError:
        parsed = None
    if parsed is not None:
        return _ensure_utc(parsed)

    cleaned = _clean_datetime_text(normalized)
    if cleaned is None:
        return None
    for pattern in SCRAPED_DATETIME_FORMATS:
        try:
            return datetime.strptime(cleaned[:19], pattern).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def extract_lot_actuality_dates(
    record: AuctionLotRecord,
    detail_cache: AuctionLotDetailCache | None = None,
) -> LotActualityDates:
    row = _as_mapping(record.datagrid_row)
    normalized_item = _as_mapping(record.normalized_item)
    detail_auction_payload = _detail_auction_payload(detail_cache)
    detail_lot_payload = _detail_lot_payload(detail_cache)
    raw_fields = _detail_raw_fields(detail_cache)

    return LotActualityDates(
        publication_at=_extract_datetime(
            raw_fields,
            row,
            normalized_item,
            detail_auction_payload,
            detail_lot_payload,
            structured_aliases=PUBLICATION_FIELD_ALIASES,
            raw_label_terms=RAW_PUBLICATION_LABELS,
        ),
        application_start_at=_extract_datetime(
            raw_fields,
            row,
            normalized_item,
            detail_auction_payload,
            detail_lot_payload,
            structured_aliases=APPLICATION_START_FIELD_ALIASES,
            raw_label_terms=RAW_APPLICATION_START_LABELS,
            raw_range_role="start",
        ),
        application_deadline_at=_extract_datetime(
            raw_fields,
            row,
            normalized_item,
            detail_auction_payload,
            detail_lot_payload,
            structured_aliases=APPLICATION_DEADLINE_FIELD_ALIASES,
            raw_label_terms=RAW_APPLICATION_DEADLINE_LABELS,
            raw_range_role="end",
        ),
        auction_at=_extract_datetime(
            raw_fields,
            row,
            normalized_item,
            detail_auction_payload,
            detail_lot_payload,
            structured_aliases=AUCTION_FIELD_ALIASES,
            raw_label_terms=RAW_AUCTION_LABELS,
            raw_range_role="start",
        ),
    )


def classify_lot_actuality(
    record: AuctionLotRecord,
    detail_cache: AuctionLotDetailCache | None = None,
    *,
    current_time: datetime | None = None,
    grace: timedelta = DEFAULT_ACTUALITY_GRACE,
    stale_after: timedelta = DEFAULT_STALE_AFTER,
) -> LotActualityClassification:
    current_time = _ensure_utc(current_time or datetime.now(UTC))
    dates = extract_lot_actuality_dates(record, detail_cache)
    status = _normalized_status(record.status)

    if _is_terminal_status(status):
        finished_at = _resolve_finished_at(dates, current_time=current_time)
        return LotActualityClassification(
            lifecycle_status="archived",
            finished_at=finished_at,
            archive_reason="terminal_status",
            dates=dates,
        )

    if dates.auction_at is not None and dates.auction_at <= current_time - grace:
        return LotActualityClassification(
            lifecycle_status="archived",
            finished_at=dates.auction_at,
            archive_reason="auction_finished",
            dates=dates,
        )

    if dates.application_deadline_at is not None and dates.application_deadline_at <= current_time - grace:
        return LotActualityClassification(
            lifecycle_status="expired",
            finished_at=dates.application_deadline_at,
            archive_reason="application_deadline_passed",
            dates=dates,
        )

    last_seen_at = _ensure_utc(record.last_seen_at) if getattr(record, "last_seen_at", None) is not None else None
    if last_seen_at is not None and current_time - last_seen_at > stale_after:
        return LotActualityClassification(
            lifecycle_status="stale",
            finished_at=last_seen_at + stale_after,
            archive_reason="last_seen_too_old",
            dates=dates,
        )

    return LotActualityClassification(
        lifecycle_status="active",
        finished_at=None,
        archive_reason=None,
        dates=dates,
    )


def _apply_actuality_to_record(
    record: AuctionLotRecord,
    actuality: LotActualityClassification,
    *,
    checked_at: datetime,
) -> bool:
    record.publication_at = actuality.dates.publication_at
    record.application_start_at = actuality.dates.application_start_at
    record.application_deadline_at = actuality.dates.application_deadline_at
    record.auction_at = actuality.dates.auction_at
    record.lifecycle_status = actuality.lifecycle_status
    record.finished_at = actuality.finished_at
    record.actuality_checked_at = checked_at
    if actuality.lifecycle_status == "active":
        record.archived_at = None
        record.archive_reason = None
    else:
        record.archived_at = checked_at
        record.archive_reason = actuality.archive_reason
        _clear_lot_enrichment_state(record)
    return True


async def run_lot_actuality_sweep(
    session: AsyncSession,
    *,
    limit: int,
    current_time: datetime | None = None,
    grace: timedelta = DEFAULT_ACTUALITY_GRACE,
    stale_after: timedelta = DEFAULT_STALE_AFTER,
) -> LotActualitySweepResult:
    current_time = _ensure_utc(current_time or datetime.now(UTC))
    resolved_limit = max(0, int(limit))
    if resolved_limit <= 0:
        return LotActualitySweepResult(
            candidate_count=0,
            processed_count=0,
            updated_count=0,
            active_to_non_active_count=0,
            non_active_to_active_count=0,
            skipped_count=0,
        )

    records = await _list_actuality_sweep_candidates(
        session,
        current_time=current_time,
        limit=resolved_limit,
        grace=grace,
        stale_after=stale_after,
    )
    if not records:
        return LotActualitySweepResult(
            candidate_count=0,
            processed_count=0,
            updated_count=0,
            active_to_non_active_count=0,
            non_active_to_active_count=0,
            skipped_count=0,
        )

    detail_caches = {
        cache.lot_record_id: cache
        for cache in (
            await session.scalars(
                select(AuctionLotDetailCache).where(AuctionLotDetailCache.lot_record_id.in_([record.id for record in records if record.id is not None]))
            )
        ).all()
    }

    candidate_record_ids: list[int] = []
    updated_count = 0
    active_to_non_active_count = 0
    non_active_to_active_count = 0
    skipped_count = 0

    for record in records:
        if record.id is None:
            skipped_count += 1
            continue
        candidate_record_ids.append(record.id)
        previous_status = _normalized_status(record.lifecycle_status)
        previous_checked_at = record.actuality_checked_at
        actuality = classify_lot_actuality(
            record,
            detail_caches.get(record.id),
            current_time=current_time,
            grace=grace,
            stale_after=stale_after,
        )
        if _apply_actuality_to_record(record, actuality, checked_at=current_time):
            updated_count += 1
        actuality_changed_fields = ["actuality_checked_at"]
        status_changed_fields = ["lifecycle_status", "finished_at", "archived_at", "archive_reason", "actuality_checked_at"]
        if previous_status == actuality.lifecycle_status and previous_checked_at == record.actuality_checked_at:
            continue
        if previous_status == "active" and actuality.lifecycle_status != "active":
            active_to_non_active_count += 1
            await bump_auction_lot_dataset_version(
                session,
                record,
                event_type="row_deleted",
                payload={
                    "source": "actuality_sweep",
                    "changed_fields": status_changed_fields,
                    "lifecycle_status": actuality.lifecycle_status,
                },
            )
            continue
        if previous_status != "active" and actuality.lifecycle_status == "active":
            non_active_to_active_count += 1
            await bump_auction_lot_dataset_version(
                session,
                record,
                event_type="row_updated",
                payload={
                    "source": "actuality_sweep",
                    "changed_fields": status_changed_fields,
                    "lifecycle_status": actuality.lifecycle_status,
                },
            )
            continue
        await bump_auction_lot_dataset_version(
            session,
            record,
            event_type="row_updated",
            payload={
                "source": "actuality_sweep",
                "changed_fields": actuality_changed_fields,
                "lifecycle_status": actuality.lifecycle_status,
            },
        )

    return LotActualitySweepResult(
        candidate_count=len(records),
        processed_count=len(records),
        updated_count=updated_count,
        active_to_non_active_count=active_to_non_active_count,
        non_active_to_active_count=non_active_to_active_count,
        skipped_count=skipped_count,
        candidate_record_ids=candidate_record_ids,
    )


async def _list_actuality_sweep_candidates(
    session: AsyncSession,
    *,
    current_time: datetime,
    limit: int,
    grace: timedelta,
    stale_after: timedelta,
) -> list[AuctionLotRecord]:
    grace_cutoff = current_time - grace
    stale_cutoff = current_time - stale_after
    refresh_cutoff = current_time - grace
    statement = (
        select(AuctionLotRecord)
        .where(
            AuctionLotRecord.lifecycle_status == "active",
        )
        .where(
            or_(
                AuctionLotRecord.actuality_checked_at.is_(None),
                AuctionLotRecord.actuality_checked_at <= refresh_cutoff,
            )
        )
        .where(
            or_(
                AuctionLotRecord.actuality_checked_at.is_(None),
                AuctionLotRecord.application_deadline_at <= grace_cutoff,
                AuctionLotRecord.auction_at <= grace_cutoff,
                AuctionLotRecord.last_seen_at <= stale_cutoff,
            )
        )
        .order_by(
            case((AuctionLotRecord.actuality_checked_at.is_(None), 0), else_=1),
            AuctionLotRecord.last_seen_at.asc(),
            AuctionLotRecord.actuality_checked_at.asc().nulls_first(),
            AuctionLotRecord.id.asc(),
        )
        .limit(limit)
    )
    return (await session.scalars(statement)).all()


def _extract_datetime(
    raw_fields: list[dict[str, Any]],
    *payloads: Mapping[str, Any],
    structured_aliases: Sequence[str],
    raw_label_terms: Sequence[str],
    raw_range_role: str = "single",
) -> datetime | None:
    for payload in payloads:
        text = _find_text_by_alias(payload, structured_aliases)
        parsed = parse_lot_datetime(text)
        if parsed is not None:
            return parsed

    raw_text = _extract_raw_field_text(raw_fields, raw_label_terms, range_role=raw_range_role)
    return parse_lot_datetime(raw_text)


def _extract_raw_field_text(
    raw_fields: list[dict[str, Any]],
    label_terms: Sequence[str],
    *,
    range_role: str = "single",
) -> str | None:
    normalized_terms = {_normalized_key(term) for term in label_terms}
    for field in raw_fields:
        field_name = _normalized_key(field.get("name"))
        if not field_name or not any(term in field_name for term in normalized_terms):
            continue
        value = _first_text(field.get("value"))
        if value is None:
            continue
        range_start, range_end = _raw_datetime_range(value)
        if range_role == "start" and range_start:
            return range_start
        if range_role == "end" and range_end:
            return range_end
        cleaned = _clean_datetime_text(value)
        return cleaned or value
    return None


def _raw_datetime_range(value: str) -> tuple[str | None, str | None]:
    normalized = value.strip()
    match = re.search(r"\bс\s+(.+?)\s+до\s+(.+)$", normalized, re.IGNORECASE)
    if not match:
        return None, _clean_datetime_text(normalized)
    return _clean_datetime_text(match.group(1)), _clean_datetime_text(match.group(2))


def _clean_datetime_text(value: object) -> str | None:
    normalized = _first_text(value)
    if not normalized:
        return None
    normalized = normalized.replace("\xa0", " ")
    normalized = re.sub(
        r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b",
        lambda match: f"{int(match.group(1)):02d}.{int(match.group(2)):02d}.{match.group(3)}",
        normalized,
    )
    return normalized.strip(" .;,")


def _find_text_by_alias(payload: object, aliases: Sequence[str]) -> str | None:
    alias_set = {_normalized_key(alias) for alias in aliases}
    return _find_text_by_alias_recursive(payload, alias_set)


def _find_text_by_alias_recursive(payload: object, aliases: set[str]) -> str | None:
    if isinstance(payload, str):
        return None
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            normalized_key = _normalized_key(key)
            if normalized_key in aliases:
                text = _first_text(value)
                if text is not None:
                    return text
            nested = _find_text_by_alias_recursive(value, aliases)
            if nested is not None:
                return nested
        return None
    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        for item in payload:
            nested = _find_text_by_alias_recursive(item, aliases)
            if nested is not None:
                return nested
    return None


def _detail_raw_fields(detail_cache: AuctionLotDetailCache | None) -> list[dict[str, Any]]:
    if detail_cache is None:
        return []
    fields: list[dict[str, Any]] = []
    for payload in (detail_cache.lot_detail, detail_cache.auction_detail):
        raw_fields = _as_mapping(payload or {}).get("raw_fields")
        if isinstance(raw_fields, list):
            fields.extend(dict(field) for field in raw_fields if isinstance(field, Mapping))
    return fields


def _detail_lot_payload(detail_cache: AuctionLotDetailCache | None) -> dict[str, Any]:
    if detail_cache is None:
        return {}
    payload = _as_mapping(detail_cache.lot_detail)
    return _as_mapping(payload.get("lot"))


def _detail_auction_payload(detail_cache: AuctionLotDetailCache | None) -> dict[str, Any]:
    if detail_cache is None:
        return {}
    payload = _as_mapping(detail_cache.auction_detail)
    return _as_mapping(payload.get("auction"))


def _clear_lot_enrichment_state(record: AuctionLotRecord) -> None:
    record.enrichment_requested_at = None
    record.last_enrichment_attempt_at = None
    record.enrichment_attempt_count = 0
    record.next_enrichment_attempt_at = None
    record.last_enrichment_error = None
    record.enrichment_claimed_at = None
    record.enrichment_claimed_by = None
    record.enrichment_claim_expires_at = None


def _resolve_finished_at(dates: LotActualityDates, *, current_time: datetime) -> datetime | None:
    if dates.auction_at is not None and dates.auction_at <= current_time:
        return dates.auction_at
    if dates.application_deadline_at is not None and dates.application_deadline_at <= current_time:
        return dates.application_deadline_at
    return current_time


def _is_terminal_status(status: str | None) -> bool:
    if not isinstance(status, str):
        return False
    normalized = status.strip().lower()
    if not normalized:
        return False
    return any(marker in normalized for marker in TERMINAL_LOT_STATUS_MARKERS)


def _normalized_status(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().lower()


def _normalized_key(value: object) -> str:
    return re.sub(r"[^0-9a-zа-яё]+", "", str(value).strip().lower())


def _as_mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _first_text(*values: object) -> str | None:
    for value in values:
        if not isinstance(value, str):
            continue
        normalized = value.strip()
        if normalized:
            return normalized
    return None


def _ensure_utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)
