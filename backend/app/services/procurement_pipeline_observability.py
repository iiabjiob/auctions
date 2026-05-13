from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.procurement import ProcurementLotRecord, ProcurementSourceSyncState
from app.schemas.procurement_pipeline_observability import (
    ProcurementPipelineCounters,
    ProcurementPipelineHealthResponse,
    ProcurementSourceSyncStatus,
)
from app.services.procurement_scoring import PROCUREMENT_SCORING_VERSION
from app.services.procurement_sources import SOURCE_PROVIDERS


async def get_procurement_pipeline_health(
    session: AsyncSession,
    *,
    current_time: datetime | None = None,
) -> ProcurementPipelineHealthResponse:
    current_time = current_time or datetime.now(UTC)
    row = (await session.execute(build_procurement_pipeline_counters_statement(current_time=current_time))).one()
    counters = ProcurementPipelineCounters(
        total_lots=int(row.total_lots or 0),
        priority_lots=int(row.priority_lots or 0),
        decision_pending_lots=int(row.decision_pending_lots or 0),
        missing_documents=int(row.missing_documents or 0),
        missing_critical_fields=int(row.missing_critical_fields or 0),
        scoring_stale_or_incomplete=int(row.scoring_stale_or_incomplete or 0),
        scored_current=int(row.scored_current or 0),
    )
    sources = await list_procurement_source_sync_statuses(session)
    return ProcurementPipelineHealthResponse(counters=counters, sources=sources)


async def list_procurement_source_sync_statuses(session: AsyncSession) -> list[ProcurementSourceSyncStatus]:
    states = {
        state.source_code: state
        for state in (await session.execute(select(ProcurementSourceSyncState))).scalars().all()
    }
    statuses = [
        build_procurement_source_sync_status(provider.info(), sync_state=states.get(provider.info().code))
        for provider in SOURCE_PROVIDERS.values()
    ]
    return sorted(statuses, key=lambda status: status.code)


def build_procurement_source_sync_status(info, *, sync_state: ProcurementSourceSyncState | None = None):  # noqa: ANN001
    return ProcurementSourceSyncStatus(
        code=info.code,
        title=info.title,
        enabled=bool(info.enabled),
        website=info.website,
        parser_version=sync_state.parser_version if sync_state is not None else getattr(SOURCE_PROVIDERS.get(info.code), "parser_version", None),
        last_sync_started_at=sync_state.last_sync_started_at if sync_state is not None else None,
        last_sync_completed_at=sync_state.last_sync_completed_at if sync_state is not None else None,
        last_successful_sync_at=sync_state.last_successful_sync_at if sync_state is not None else None,
        last_sync_result=sync_state.last_sync_result if sync_state is not None else None,
        last_sync_error=sync_state.last_sync_error if sync_state is not None else None,
        last_sync_error_code=sync_state.last_sync_error_code if sync_state is not None else None,
        last_sync_fetched=sync_state.last_sync_fetched if sync_state is not None else None,
        last_sync_created=sync_state.last_sync_created if sync_state is not None else None,
        last_sync_updated=sync_state.last_sync_updated if sync_state is not None else None,
        last_sync_unchanged=sync_state.last_sync_unchanged if sync_state is not None else None,
        last_sync_status_changed=sync_state.last_sync_status_changed if sync_state is not None else None,
        last_sync_parser_failures=sync_state.last_sync_parser_failures if sync_state is not None else None,
        last_sync_missing_critical_fields=(
            dict(sync_state.last_sync_missing_critical_fields or {}) if sync_state is not None else {}
        ),
    )


def build_procurement_pipeline_counters_statement(*, current_time: datetime | None = None):  # noqa: ARG001
    missing_documents_clause = and_(
        ProcurementLotRecord.documentation_present.is_not(True),
        ProcurementLotRecord.documents_url.is_(None),
        ProcurementLotRecord.specification_url.is_(None),
    )
    missing_critical_clause = or_(
        ProcurementLotRecord.title.is_(None),
        ProcurementLotRecord.title == "",
        ProcurementLotRecord.initial_price_value.is_(None),
        ProcurementLotRecord.application_deadline_at.is_(None),
        ProcurementLotRecord.notice_url.is_(None),
        ProcurementLotRecord.notice_url == "",
    )
    scoring_stale_clause = or_(
        ProcurementLotRecord.scoring_version != PROCUREMENT_SCORING_VERSION,
        ProcurementLotRecord.scoring_version.is_(None),
        ProcurementLotRecord.scoring_input_hash.is_(None),
        ProcurementLotRecord.scored_at.is_(None),
    )
    scored_current_clause = and_(
        ProcurementLotRecord.scoring_version == PROCUREMENT_SCORING_VERSION,
        ProcurementLotRecord.scoring_input_hash.is_not(None),
        ProcurementLotRecord.scored_at.is_not(None),
    )
    return select(
        func.count(ProcurementLotRecord.id).label("total_lots"),
        func.count().filter(ProcurementLotRecord.attractiveness_score >= 75).label("priority_lots"),
        func.count().filter(ProcurementLotRecord.workflow_status == "decision").label("decision_pending_lots"),
        func.count().filter(missing_documents_clause).label("missing_documents"),
        func.count().filter(missing_critical_clause).label("missing_critical_fields"),
        func.count().filter(scoring_stale_clause).label("scoring_stale_or_incomplete"),
        func.count().filter(scored_current_clause).label("scored_current"),
    )
