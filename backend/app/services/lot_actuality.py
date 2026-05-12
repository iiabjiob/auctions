from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.auction import AuctionLotDetailCache, AuctionLotRecord


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
