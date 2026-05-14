from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.procurement import (
    ProcurementLotDetailCache,
    ProcurementLotDetailObservation,
    ProcurementLotObservation,
    ProcurementLotRecord,
)
from app.schemas.procurements import (
    ProcurementDocument,
    ProcurementRawField,
    ProcurementWorkspaceChangeSummary,
    ProcurementWorkspaceEnrichmentState,
    ProcurementWorkspaceRefreshResponse,
    ProcurementWorkspaceResponse,
)
from app.services.procurement_catalog import procurement_lot_response
from app.services.procurement_enrichment import enrich_procurement_lot_record


async def get_procurement_lot_workspace(
    session: AsyncSession,
    *,
    source: str,
    external_id: str,
    refresh: bool = False,
    include_detail: bool = True,
) -> ProcurementWorkspaceResponse:
    record = await find_procurement_lot_record(session, source=source, external_id=external_id)
    if record is None:
        raise LookupError("Procurement lot record was not found in persisted catalog")
    if refresh:
        await enrich_procurement_lot_record(session, record)
        await session.commit()
    detail_cache = await get_procurement_lot_detail_cache(session, record) if include_detail or refresh else None
    return await build_procurement_workspace_response(session, record, detail_cache)


async def refresh_procurement_lot_workspace_live(
    session: AsyncSession,
    *,
    source: str,
    external_id: str,
) -> ProcurementWorkspaceRefreshResponse:
    workspace = await get_procurement_lot_workspace(
        session,
        source=source,
        external_id=external_id,
        refresh=True,
        include_detail=True,
    )
    return ProcurementWorkspaceRefreshResponse(status="refreshed", refreshed=True, workspace=workspace)


async def find_procurement_lot_record(
    session: AsyncSession,
    *,
    source: str,
    external_id: str,
) -> ProcurementLotRecord | None:
    return await session.scalar(
        select(ProcurementLotRecord).where(
            ProcurementLotRecord.source_code == source,
            ProcurementLotRecord.external_id == external_id,
        )
    )


async def get_procurement_lot_detail_cache(
    session: AsyncSession,
    record: ProcurementLotRecord,
) -> ProcurementLotDetailCache | None:
    if record.id is None:
        return None
    return await session.scalar(
        select(ProcurementLotDetailCache).where(ProcurementLotDetailCache.procurement_lot_record_id == record.id)
    )


async def build_procurement_workspace_response(
    session: AsyncSession,
    record: ProcurementLotRecord,
    detail_cache: ProcurementLotDetailCache | None,
) -> ProcurementWorkspaceResponse:
    return ProcurementWorkspaceResponse(
        record=procurement_lot_response(record),
        detail_cached_at=detail_cache.fetched_at if detail_cache is not None else None,
        detail_payload=dict(detail_cache.detail_payload or {}) if detail_cache is not None else None,
        documents=_documents_from_cache(detail_cache),
        raw_fields=_raw_fields_from_cache(detail_cache),
        changes=await _change_summary(session, record),
        current_enrichment_state=_enrichment_state(record),
    )


def _documents_from_cache(detail_cache: ProcurementLotDetailCache | None) -> list[ProcurementDocument]:
    if detail_cache is None:
        return []
    return [
        ProcurementDocument(
            title=str(document.get("title")) if document.get("title") is not None else None,
            url=str(document.get("url")) if document.get("url") is not None else None,
            source_url=str(document.get("source_url")) if document.get("source_url") is not None else None,
        )
        for document in (detail_cache.documents or [])
        if isinstance(document, Mapping)
    ]


def _raw_fields_from_cache(detail_cache: ProcurementLotDetailCache | None) -> list[ProcurementRawField]:
    if detail_cache is None:
        return []
    detail_payload = detail_cache.detail_payload or {}
    fields = detail_payload.get("fields") if isinstance(detail_payload, Mapping) else None
    if not isinstance(fields, Mapping):
        return []
    return [
        ProcurementRawField(name=str(name), value=str(value))
        for name, value in fields.items()
        if value is not None and str(value).strip()
    ][:200]


async def _change_summary(session: AsyncSession, record: ProcurementLotRecord) -> ProcurementWorkspaceChangeSummary:
    if record.id is None:
        return ProcurementWorkspaceChangeSummary()
    observations_count = int(
        await session.scalar(
            select(func.count()).select_from(ProcurementLotObservation).where(
                ProcurementLotObservation.procurement_lot_record_id == record.id
            )
        )
        or 0
    )
    detail_observations_count = int(
        await session.scalar(
            select(func.count()).select_from(ProcurementLotDetailObservation).where(
                ProcurementLotDetailObservation.procurement_lot_record_id == record.id
            )
        )
        or 0
    )
    last_observation = await session.scalar(
        select(ProcurementLotObservation)
        .where(ProcurementLotObservation.procurement_lot_record_id == record.id)
        .order_by(ProcurementLotObservation.observed_at.desc(), ProcurementLotObservation.id.desc())
        .limit(1)
    )
    previous_observation = await session.scalar(
        select(ProcurementLotObservation)
        .where(ProcurementLotObservation.procurement_lot_record_id == record.id)
        .order_by(ProcurementLotObservation.observed_at.desc(), ProcurementLotObservation.id.desc())
        .offset(1)
        .limit(1)
    )
    last_detail_observed_at = await session.scalar(
        select(func.max(ProcurementLotDetailObservation.observed_at)).where(
            ProcurementLotDetailObservation.procurement_lot_record_id == record.id
        )
    )
    return ProcurementWorkspaceChangeSummary(
        observations_count=observations_count,
        detail_observations_count=detail_observations_count,
        last_observed_at=last_observation.observed_at if last_observation is not None else None,
        last_detail_observed_at=last_detail_observed_at,
        changed_fields=_changed_fields(previous_observation, last_observation),
    )


def _changed_fields(
    previous_observation: ProcurementLotObservation | None,
    last_observation: ProcurementLotObservation | None,
) -> list[str]:
    if previous_observation is None or last_observation is None:
        return []
    previous = previous_observation.normalized_item if isinstance(previous_observation.normalized_item, Mapping) else {}
    current = last_observation.normalized_item if isinstance(last_observation.normalized_item, Mapping) else {}
    keys = set(previous) | set(current)
    return sorted(str(key) for key in keys if previous.get(key) != current.get(key))[:80]


def _enrichment_state(record: ProcurementLotRecord) -> ProcurementWorkspaceEnrichmentState:
    return ProcurementWorkspaceEnrichmentState(
        requested_at=record.enrichment_requested_at,
        requested_reason=record.enrichment_requested_reason,
        last_attempt_at=record.last_enrichment_attempt_at,
        attempt_count=int(record.enrichment_attempt_count or 0),
        next_attempt_at=record.next_enrichment_attempt_at,
        last_error=record.last_enrichment_error,
        claimed_at=record.enrichment_claimed_at,
        claimed_by=record.enrichment_claimed_by,
        claim_expires_at=record.enrichment_claim_expires_at,
    )
