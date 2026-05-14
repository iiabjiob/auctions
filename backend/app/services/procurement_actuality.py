from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.procurement import ProcurementLotRecord
from app.services.procurement_grid_state import bump_procurement_lot_dataset_version


TERMINAL_PROCUREMENT_STATUS_MARKERS: tuple[str, ...] = (
    "заверш",
    "закупка завершена",
    "исполнение завершено",
    "отмен",
    "аннулир",
    "несостоя",
    "подвед",
)
DEFAULT_PROCUREMENT_ACTUALITY_GRACE = timedelta(hours=24)
DEFAULT_PROCUREMENT_STALE_AFTER = timedelta(days=30)
SCRAPED_DATETIME_FORMATS: tuple[str, ...] = (
    "%d.%m.%Y %H:%M:%S",
    "%d.%m.%Y %H:%M",
    "%d.%m.%Y",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
)


class ProcurementActualityClassification(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    lifecycle_status: str
    finished_at: datetime | None = None
    archive_reason: str | None = None


class ProcurementActualitySweepResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_count: int
    processed_count: int
    updated_count: int
    active_to_non_active_count: int
    non_active_to_active_count: int
    skipped_count: int
    candidate_record_ids: list[int] = Field(default_factory=list)


def parse_procurement_datetime(value: str | None) -> datetime | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized:
        return None
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        parsed = None
    if parsed is not None:
        return _ensure_utc(parsed)
    cleaned = re.sub(r"\s+", " ", normalized.replace("\xa0", " ")).strip(" .;,")
    for pattern in SCRAPED_DATETIME_FORMATS:
        try:
            return datetime.strptime(cleaned[:19], pattern).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def classify_procurement_actuality(
    record: ProcurementLotRecord,
    *,
    current_time: datetime | None = None,
    grace: timedelta = DEFAULT_PROCUREMENT_ACTUALITY_GRACE,
    stale_after: timedelta = DEFAULT_PROCUREMENT_STALE_AFTER,
) -> ProcurementActualityClassification:
    current_time = _ensure_utc(current_time or datetime.now(UTC))
    status = _normalized_status(record.status)
    deadline_at = _ensure_utc(record.application_deadline_at) if record.application_deadline_at is not None else None
    last_seen_at = _ensure_utc(record.last_seen_at) if record.last_seen_at is not None else None

    if _is_terminal_status(status):
        return ProcurementActualityClassification(
            lifecycle_status="archived",
            finished_at=_resolve_finished_at(deadline_at=deadline_at, current_time=current_time),
            archive_reason="terminal_status",
        )
    if deadline_at is not None and deadline_at <= current_time - grace:
        return ProcurementActualityClassification(
            lifecycle_status="expired",
            finished_at=deadline_at,
            archive_reason="application_deadline_passed",
        )
    if last_seen_at is not None and current_time - last_seen_at > stale_after:
        return ProcurementActualityClassification(
            lifecycle_status="stale",
            finished_at=last_seen_at + stale_after,
            archive_reason="last_seen_too_old",
        )
    return ProcurementActualityClassification(lifecycle_status="active")


async def run_procurement_actuality_sweep(
    session: AsyncSession,
    *,
    limit: int,
    current_time: datetime | None = None,
    grace: timedelta = DEFAULT_PROCUREMENT_ACTUALITY_GRACE,
    stale_after: timedelta = DEFAULT_PROCUREMENT_STALE_AFTER,
) -> ProcurementActualitySweepResult:
    current_time = _ensure_utc(current_time or datetime.now(UTC))
    resolved_limit = max(0, int(limit))
    if resolved_limit <= 0:
        return _empty_result()

    records = await _list_actuality_sweep_candidates(
        session,
        current_time=current_time,
        limit=resolved_limit,
        grace=grace,
        stale_after=stale_after,
    )
    if not records:
        return _empty_result()

    candidate_record_ids: list[int] = []
    updated_count = 0
    active_to_non_active_count = 0
    non_active_to_active_count = 0
    skipped_count = 0

    for record in records:
        if record.id is None:
            skipped_count += 1
            continue
        candidate_record_ids.append(int(record.id))
        previous_status = _normalized_status(record.lifecycle_status)
        previous_checked_at = record.actuality_checked_at
        actuality = classify_procurement_actuality(record, current_time=current_time, grace=grace, stale_after=stale_after)
        _apply_actuality_to_record(record, actuality, checked_at=current_time)
        updated_count += 1
        if previous_status == actuality.lifecycle_status and previous_checked_at == record.actuality_checked_at:
            continue
        status_changed_fields = ["lifecycle_status", "finished_at", "archived_at", "archive_reason", "actuality_checked_at"]
        if previous_status == "active" and actuality.lifecycle_status != "active":
            active_to_non_active_count += 1
            await bump_procurement_lot_dataset_version(
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
            await bump_procurement_lot_dataset_version(
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
        await bump_procurement_lot_dataset_version(
            session,
            record,
            event_type="row_updated",
            payload={
                "source": "actuality_sweep",
                "changed_fields": ["actuality_checked_at"],
                "lifecycle_status": actuality.lifecycle_status,
            },
        )

    return ProcurementActualitySweepResult(
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
) -> list[ProcurementLotRecord]:
    grace_cutoff = current_time - grace
    stale_cutoff = current_time - stale_after
    refresh_cutoff = current_time - grace
    deadline_expression = func.coalesce(ProcurementLotRecord.application_deadline_at, datetime.max.replace(tzinfo=UTC))
    statement = (
        select(ProcurementLotRecord)
        .where(ProcurementLotRecord.lifecycle_status == "active")
        .where(
            or_(
                ProcurementLotRecord.actuality_checked_at.is_(None),
                ProcurementLotRecord.actuality_checked_at <= refresh_cutoff,
            )
        )
        .where(
            or_(
                ProcurementLotRecord.actuality_checked_at.is_(None),
                ProcurementLotRecord.application_deadline_at <= grace_cutoff,
                ProcurementLotRecord.last_seen_at <= stale_cutoff,
            )
        )
        .order_by(
            ProcurementLotRecord.attractiveness_score.desc(),
            deadline_expression.asc(),
            ProcurementLotRecord.last_seen_at.desc(),
            ProcurementLotRecord.actuality_checked_at.asc().nulls_first(),
            ProcurementLotRecord.id.asc(),
        )
        .limit(limit)
    )
    return list((await session.scalars(statement)).all())


def _apply_actuality_to_record(
    record: ProcurementLotRecord,
    actuality: ProcurementActualityClassification,
    *,
    checked_at: datetime,
) -> None:
    record.lifecycle_status = actuality.lifecycle_status
    record.finished_at = actuality.finished_at
    record.actuality_checked_at = checked_at
    if actuality.lifecycle_status == "active":
        record.archived_at = None
        record.archive_reason = None
        return
    record.archived_at = checked_at
    record.archive_reason = actuality.archive_reason
    _clear_procurement_enrichment_state(record)


def _clear_procurement_enrichment_state(record: ProcurementLotRecord) -> None:
    record.enrichment_requested_at = None
    record.enrichment_requested_reason = None
    record.last_enrichment_attempt_at = None
    record.enrichment_attempt_count = 0
    record.next_enrichment_attempt_at = None
    record.last_enrichment_error = None
    record.enrichment_claimed_at = None
    record.enrichment_claimed_by = None
    record.enrichment_claim_expires_at = None


def _empty_result() -> ProcurementActualitySweepResult:
    return ProcurementActualitySweepResult(
        candidate_count=0,
        processed_count=0,
        updated_count=0,
        active_to_non_active_count=0,
        non_active_to_active_count=0,
        skipped_count=0,
    )


def _resolve_finished_at(*, deadline_at: datetime | None, current_time: datetime) -> datetime:
    if deadline_at is not None and deadline_at <= current_time:
        return deadline_at
    return current_time


def _is_terminal_status(status: str | None) -> bool:
    if not status:
        return False
    return any(marker in status for marker in TERMINAL_PROCUREMENT_STATUS_MARKERS)


def _normalized_status(value: object) -> str:
    return str(value).strip().lower() if isinstance(value, str) else ""


def _ensure_utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)
