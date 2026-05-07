from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import and_, cast, func, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auction import AuctionLotRecord, AuctionSourceState
from app.schemas.auction_pipeline_observability import AuctionPipelineCounters
from app.services.auction_scoring import SCORING_VERSION


DEFAULT_ENRICHMENT_TTL_OBSERVABILITY_SECONDS = 7 * 24 * 60 * 60


async def get_auction_pipeline_counters(
    session: AsyncSession,
    *,
    current_time: datetime | None = None,
) -> AuctionPipelineCounters:
    current_time = current_time or datetime.now(UTC)
    statement = build_auction_pipeline_counters_statement(current_time=current_time)
    row = (await session.execute(statement)).one()
    return AuctionPipelineCounters.model_validate(
        {
            "enrichment_requested": int(row.enrichment_requested or 0),
            "enrichment_due_now": int(row.enrichment_due_now or 0),
            "enrichment_claimed_active": int(row.enrichment_claimed_active or 0),
            "enrichment_retry_waiting": int(row.enrichment_retry_waiting or 0),
            "enrichment_failed_with_error": int(row.enrichment_failed_with_error or 0),
            "scoring_stale_or_incomplete": int(row.scoring_stale_or_incomplete or 0),
            "scored_current": int(row.scored_current or 0),
        }
    )


def build_auction_pipeline_counters_statement(*, current_time: datetime | None = None):
    current_time = current_time or datetime.now(UTC)
    source_enabled_clause = AuctionSourceState.enabled.is_(True)
    terminal_clause = ~_terminal_status_clause()
    active_claim_clause = and_(
        AuctionLotRecord.enrichment_claimed_at.is_not(None),
        or_(
            AuctionLotRecord.enrichment_claim_expires_at.is_(None),
            AuctionLotRecord.enrichment_claim_expires_at > current_time,
        ),
    )
    retry_waiting_clause = and_(
        AuctionLotRecord.enrichment_requested_at.is_not(None),
        AuctionLotRecord.next_enrichment_attempt_at.is_not(None),
        AuctionLotRecord.next_enrichment_attempt_at > current_time,
    )
    due_now_clause = and_(
        AuctionLotRecord.enrichment_requested_at.is_not(None),
        or_(
            AuctionLotRecord.next_enrichment_attempt_at.is_(None),
            AuctionLotRecord.next_enrichment_attempt_at <= current_time,
        ),
        or_(
            AuctionLotRecord.enrichment_claimed_at.is_(None),
            AuctionLotRecord.enrichment_claim_expires_at.is_(None),
            AuctionLotRecord.enrichment_claim_expires_at <= current_time,
        ),
        source_enabled_clause,
        terminal_clause,
    )
    requested_clause = and_(AuctionLotRecord.enrichment_requested_at.is_not(None), source_enabled_clause, terminal_clause)
    failed_clause = and_(
        AuctionLotRecord.last_enrichment_error.is_not(None),
        AuctionLotRecord.enrichment_requested_at.is_not(None),
        source_enabled_clause,
        terminal_clause,
    )
    stale_or_incomplete_clause = or_(
        AuctionLotRecord.scoring_version != SCORING_VERSION,
        AuctionLotRecord.score_input_hash.is_(None),
        AuctionLotRecord.scored_at.is_(None),
        AuctionLotRecord.score_breakdown.is_(None),
        AuctionLotRecord.score_breakdown == cast({}, JSONB),
    )
    current_score_clause = and_(
        AuctionLotRecord.scoring_version == SCORING_VERSION,
        AuctionLotRecord.score_input_hash.is_not(None),
        AuctionLotRecord.scored_at.is_not(None),
        AuctionLotRecord.score_breakdown.is_not(None),
        AuctionLotRecord.score_breakdown != cast({}, JSONB),
    )
    statement = (
        select(
            func.count(AuctionLotRecord.id).filter(requested_clause).label("enrichment_requested"),
            func.count(AuctionLotRecord.id).filter(due_now_clause).label("enrichment_due_now"),
            func.count(AuctionLotRecord.id).filter(active_claim_clause).label("enrichment_claimed_active"),
            func.count(AuctionLotRecord.id).filter(retry_waiting_clause).label("enrichment_retry_waiting"),
            func.count(AuctionLotRecord.id).filter(failed_clause).label("enrichment_failed_with_error"),
            func.count(AuctionLotRecord.id).filter(and_(stale_or_incomplete_clause, source_enabled_clause)).label("scoring_stale_or_incomplete"),
            func.count(AuctionLotRecord.id).filter(and_(current_score_clause, source_enabled_clause)).label("scored_current"),
        )
        .select_from(AuctionLotRecord)
        .join(AuctionSourceState, AuctionSourceState.code == AuctionLotRecord.source_code)
    )
    return statement


def _terminal_status_clause():
    status_text = func.lower(func.coalesce(AuctionLotRecord.status, ""))
    return or_(
        status_text.contains("архив"),
        status_text.contains("archived"),
        status_text.contains("заверш"),
        status_text.contains("отмен"),
    )
