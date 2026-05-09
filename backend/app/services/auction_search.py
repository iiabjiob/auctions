from __future__ import annotations

import re
from typing import Any

from app.models.auction import AuctionLotRecord


SEARCH_TEXT_FIELDS = (
    "lot_name",
    "source_title",
    "location_region",
    "category",
    "organizer_name",
    "debtor_name",
    "location",
)


def build_lot_search_text(
    *,
    datagrid_row: dict[str, Any] | None,
    normalized_item: dict[str, Any] | None = None,
    lot_name: str | None = None,
) -> str:
    row = datagrid_row if isinstance(datagrid_row, dict) else {}
    normalized = normalized_item if isinstance(normalized_item, dict) else {}
    lot = normalized.get("lot") if isinstance(normalized.get("lot"), dict) else {}
    organizer = normalized.get("organizer") if isinstance(normalized.get("organizer"), dict) else {}
    debtor = normalized.get("debtor") if isinstance(normalized.get("debtor"), dict) else {}

    values = [
        lot_name or _text(row.get("lot_name")) or _text(lot.get("name")),
        _text(row.get("source_title")),
        _text(row.get("location_region")) or _text(row.get("region")) or _text(lot.get("region")),
        _text(row.get("category")) or _text(row.get("model_category")) or _text(lot.get("category")),
        _text(row.get("organizer_name")) or _text(organizer.get("name")),
        _text(row.get("debtor_name")) or _text(debtor.get("name")),
        _text(row.get("location")) or _text(lot.get("location")),
    ]
    return normalize_search_text(" ".join(value for value in values if value))


def normalize_search_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def update_record_search_text(record: AuctionLotRecord) -> None:
    record.search_text = build_lot_search_text(
        datagrid_row=record.datagrid_row if isinstance(record.datagrid_row, dict) else None,
        normalized_item=record.normalized_item if isinstance(record.normalized_item, dict) else None,
        lot_name=record.lot_name,
    )


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None
