from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.models.auction import AuctionLotDetailCache, AuctionLotRecord
from app.schemas.lot_evidence import (
    LotCategoryFacts,
    LotConstraintFacts,
    LotDeadlineFacts,
    LotEvidence,
    LotFreshnessFacts,
    LotLegalFacts,
    LotLocationFacts,
    LotPriceFacts,
    build_lot_evidence_hash,
)
from app.services.auction_analysis import DEFAULT_EXCLUSION_KEYWORDS, DEFAULT_LEGAL_RISK_RULES
from app.services.auction_datagrid_payload import validate_datagrid_row_payload
from app.services.auction_values import parse_price


MEDIA_DOCUMENT_PATTERN = re.compile(r"фото|photo|изображ|\.rar|\.zip|\.7z|\.jpe?g|\.png|\.webp", re.IGNORECASE)
DEADLINE_PATTERNS = (
    "%d.%m.%Y %H:%M:%S",
    "%d.%m.%Y %H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%Y-%m-%dT%H:%M:%S",
)


def build_lot_evidence(record: AuctionLotRecord, detail_cache: AuctionLotDetailCache | None = None) -> LotEvidence:
    row = validate_datagrid_row_payload(record.datagrid_row)
    normalized_item = record.normalized_item or {}
    lot_payload = _as_mapping(normalized_item.get("lot"))
    auction_payload = _as_mapping(normalized_item.get("auction"))
    detail_lot_payload = _detail_lot_payload(detail_cache)
    detail_auction_payload = _detail_auction_payload(detail_cache)

    merged_lot = {**lot_payload, **detail_lot_payload}
    merged_auction = {**auction_payload, **detail_auction_payload}
    search_text = _build_search_text(record, row, detail_cache)

    documents = tuple((detail_cache.documents or []) if detail_cache else [])
    media_document_count = sum(1 for document in documents if _is_media_document(document))
    application_start, application_deadline, auction_date = _extract_deadlines(detail_cache, row, merged_auction, merged_lot)

    return LotEvidence(
        source_code=record.source_code,
        auction_external_id=record.auction_external_id,
        lot_external_id=record.lot_external_id,
        lot_number=record.lot_number,
        content_hash=record.content_hash,
        detail_content_hash=detail_cache.content_hash if detail_cache else None,
        price=LotPriceFacts(
            initial_price=_resolve_decimal(
                merged_lot.get("initial_price"),
                record.initial_price,
            ),
            current_price=_resolve_decimal(
                merged_lot.get("current_price"),
                record.initial_price,
            ),
            minimum_price=_resolve_decimal(
                merged_lot.get("minimum_price"),
            ),
            market_value=_resolve_decimal(
                merged_lot.get("market_value"),
            ),
            currency=_first_text(
                merged_lot.get("currency"),
                merged_auction.get("currency"),
            ),
        ),
        location=LotLocationFacts(
            region=_first_text(row.location_region, merged_lot.get("region")),
            city=_first_text(row.location_city, merged_lot.get("city")),
            address=_first_text(row.location_address, merged_lot.get("address")),
            coordinates=_first_text(row.location_coordinates, merged_lot.get("coordinates")),
        ),
        category=LotCategoryFacts(
            category=_first_text(merged_lot.get("category")),
            model_category=_first_text(merged_lot.get("model_category")),
            lot_name=_first_text(row.lot_name, record.lot_name),
            status=_first_text(merged_lot.get("status"), row.status, record.status),
        ),
        legal=LotLegalFacts(
            has_documents=bool(documents),
            has_photos=bool(row.primary_image_url or row.images or media_document_count),
            document_count=len(documents),
            media_document_count=media_document_count,
            exclusion_signals=_collect_keyword_hits(search_text, DEFAULT_EXCLUSION_KEYWORDS),
            legal_risk_signals=_collect_keyword_hits(
                search_text,
                (
                    *DEFAULT_LEGAL_RISK_RULES.high_keywords,
                    *DEFAULT_LEGAL_RISK_RULES.medium_keywords,
                    *DEFAULT_LEGAL_RISK_RULES.medium_categories,
                ),
            ),
        ),
        deadlines=LotDeadlineFacts(
            application_start=application_start,
            application_deadline=application_deadline,
            auction_date=auction_date,
            hours_to_deadline=_hours_to_deadline(application_deadline),
        ),
        constraints=LotConstraintFacts(
            inspection_order=_first_text(
                merged_lot.get("inspection_order"),
                detail_lot_payload.get("inspection_order"),
            ),
            description_present=bool(
                _first_text(
                    row.lot_description,
                    merged_lot.get("description"),
                    detail_lot_payload.get("description"),
                )
            ),
            price_schedule_steps=len(row.price_schedule),
        ),
        freshness=LotFreshnessFacts(
            is_new=bool(getattr(record, "is_new", False)),
            first_seen_at=record.first_seen_at,
            last_seen_at=record.last_seen_at,
            status_changed_at=record.status_changed_at,
            detail_fetched_at=detail_cache.fetched_at if detail_cache else None,
        ),
    )


def lot_evidence_hash(record: AuctionLotRecord, detail_cache: AuctionLotDetailCache | None = None) -> str:
    return build_lot_evidence_hash(build_lot_evidence(record, detail_cache))


def _as_mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


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


def _detail_raw_fields(detail_cache: AuctionLotDetailCache | None) -> list[dict[str, Any]]:
    if detail_cache is None:
        return []
    fields: list[dict[str, Any]] = []
    for payload in (detail_cache.lot_detail, detail_cache.auction_detail):
        raw_fields = _as_mapping(payload or {}).get("raw_fields")
        if isinstance(raw_fields, list):
            fields.extend(dict(field) for field in raw_fields if isinstance(field, Mapping))
    return fields


def _build_search_text(record: AuctionLotRecord, row, detail_cache: AuctionLotDetailCache | None) -> str:
    parts = [
        record.lot_name,
        record.status,
        row.lot_name,
        row.lot_description,
        row.category,
        row.model_category,
        row.location,
        row.location_region,
        row.location_city,
        _json_text(record.normalized_item or {}),
    ]
    if detail_cache is not None:
        parts.extend(
            [
                _json_text(detail_cache.lot_detail or {}),
                _json_text(detail_cache.auction_detail or {}),
                _json_text(detail_cache.documents or []),
            ]
        )
    return " ".join(str(part or "") for part in parts).lower()


def _json_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return " ".join(_json_text(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return " ".join(_json_text(item) for item in value)
    return str(value)


def _collect_keyword_hits(search_text: str, keywords: Sequence[str]) -> tuple[str, ...]:
    hits: list[str] = []
    seen: set[str] = set()
    for keyword in keywords:
        normalized = str(keyword or "").strip().lower()
        if not normalized or normalized in seen:
            continue
        if normalized in search_text:
            seen.add(normalized)
            hits.append(normalized)
    return tuple(hits)


def _extract_deadlines(
    detail_cache: AuctionLotDetailCache | None,
    row,
    merged_auction: Mapping[str, Any],
    merged_lot: Mapping[str, Any],
) -> tuple[str | None, str | None, str | None]:
    raw_fields = _detail_raw_fields(detail_cache)
    raw_application_start, raw_application_deadline = _raw_datetime_range(raw_fields, "Прием заявок", "Приём заявок")
    raw_auction_start, _raw_auction_deadline = _raw_datetime_range(raw_fields, "Проведение торгов", "Торги")
    application_start = _first_text(
        raw_application_start,
        merged_auction.get("application_start"),
        merged_lot.get("application_start"),
    )
    application_deadline = _first_text(
        raw_application_deadline,
        row.application_deadline,
        merged_auction.get("application_deadline"),
        merged_lot.get("application_deadline"),
    )
    auction_date = _first_text(
        raw_auction_start,
        row.auction_date,
        merged_auction.get("auction_date"),
        merged_lot.get("auction_date"),
    )
    return application_start, application_deadline, auction_date


def _hours_to_deadline(value: str | None) -> int | None:
    if not value:
        return None
    deadline = _parse_deadline(value)
    if deadline is None:
        return None
    remaining_seconds = (deadline - datetime.now(UTC).replace(tzinfo=None)).total_seconds()
    return int(remaining_seconds // 3600)


def _parse_deadline(value: str) -> datetime | None:
    normalized = value.strip()
    for pattern in DEADLINE_PATTERNS:
        try:
            return datetime.strptime(normalized[:19], pattern)
        except ValueError:
            continue
    return None


def _raw_datetime_range(fields: list[dict[str, Any]], *names: str) -> tuple[str | None, str | None]:
    value = _raw_field_value(fields, *names)
    if not value:
        return None, None
    match = re.search(r"\bс\s+(.+?)\s+до\s+(.+)$", value, re.IGNORECASE)
    if not match:
        return None, _clean_datetime_text(value)
    return _clean_datetime_text(match.group(1)), _clean_datetime_text(match.group(2))


def _raw_field_value(fields: list[dict[str, Any]], *names: str) -> str | None:
    wanted = {name.lower().rstrip(":") for name in names}
    for field in fields:
        field_name = str(field.get("name") or "").lower().rstrip(":")
        value = field.get("value")
        if field_name in wanted and isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _clean_datetime_text(value: object) -> str | None:
    normalized = _first_text(value)
    if not normalized:
        return None
    return re.sub(
        r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b",
        lambda match: f"{int(match.group(1)):02d}.{int(match.group(2)):02d}.{match.group(3)}",
        normalized,
    )


def _resolve_decimal(*values: object) -> Decimal | None:
    for value in values:
        if value is None:
            continue
        if isinstance(value, Decimal):
            return value
        if isinstance(value, int | float):
            return Decimal(str(value))
        if isinstance(value, str):
            parsed = parse_price(value)
            if parsed is not None:
                return parsed
            normalized = value.strip()
            if not normalized:
                continue
            try:
                return Decimal(normalized)
            except InvalidOperation:
                continue
    return None


def _first_text(*values: object) -> str | None:
    for value in values:
        if not isinstance(value, str):
            continue
        normalized = value.strip()
        if normalized:
            return normalized
    return None


def _is_media_document(document: object) -> bool:
    text = " ".join(str(_get_document_field(document, key) or "") for key in ["name", "document_type", "comment", "url"]).lower()
    return bool(MEDIA_DOCUMENT_PATTERN.search(text))


def _get_document_field(document: object, field_name: str) -> object:
    if isinstance(document, Mapping):
        return document.get(field_name)
    return getattr(document, field_name, None)
