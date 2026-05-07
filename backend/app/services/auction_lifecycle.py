from __future__ import annotations

from enum import StrEnum

from app.models.auction import AuctionLotDetailCache, AuctionLotRecord
from app.services.auction_scoring import record_score_is_current


class LotLifecycleState(StrEnum):
    DISCOVERED = "discovered"
    LIST_SYNCED = "list_synced"
    NEEDS_ENRICHMENT = "needs_enrichment"
    ENRICHED = "enriched"
    SCORED = "scored"
    ACTIVE = "active"
    STALE = "stale"
    ARCHIVED = "archived"


TERMINAL_LOT_LIFECYCLE_STATES: tuple[LotLifecycleState, ...] = (LotLifecycleState.ARCHIVED,)


def is_terminal_lifecycle_state(state: str | LotLifecycleState) -> bool:
    try:
        normalized_state = LotLifecycleState(str(state))
    except ValueError:
        return False
    return normalized_state in TERMINAL_LOT_LIFECYCLE_STATES


def lot_is_discovered(record: AuctionLotRecord) -> bool:
    return record.id is not None


def lot_is_list_synced(record: AuctionLotRecord) -> bool:
    return bool(record.content_hash and record.datagrid_row and record.normalized_item)


def lot_needs_enrichment(record: AuctionLotRecord, detail_cache: AuctionLotDetailCache | None = None) -> bool:
    return detail_cache is None


def lot_is_enriched(record: AuctionLotRecord, detail_cache: AuctionLotDetailCache | None = None) -> bool:
    return detail_cache is not None and bool(detail_cache.content_hash)


def lot_needs_scoring(record: AuctionLotRecord, *, input_hash: str | None = None) -> bool:
    return not record_score_is_current(record, input_hash=input_hash)


def lot_is_scored(record: AuctionLotRecord, *, input_hash: str | None = None) -> bool:
    return not lot_needs_scoring(record, input_hash=input_hash)


def lot_is_active(
    record: AuctionLotRecord,
    *,
    detail_cache: AuctionLotDetailCache | None = None,
    input_hash: str | None = None,
) -> bool:
    return lot_is_list_synced(record) and lot_is_enriched(record, detail_cache) and lot_is_scored(record, input_hash=input_hash)


def lot_is_stale(record: AuctionLotRecord, *, input_hash: str | None = None) -> bool:
    return lot_needs_scoring(record, input_hash=input_hash)
