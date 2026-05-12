from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from collections.abc import Sequence

from sqlalchemy import and_, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, ConfigDict, Field

from app.models.auction import AuctionLotDetailCache, AuctionLotRecord, AuctionSourceState
from app.schemas.lot_evidence import LotEvidence
from app.services.lot_evidence import build_lot_evidence
from app.services.auction_workspace import ensure_lot_detail_cache


class LotEnrichmentRequirementEvaluation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    needs_enrichment: bool
    missing_fields: list[str] = Field(default_factory=list)
    reason_category: str = "ready_for_scoring"


class LotEnrichmentDryRunResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_count: int
    processed_count: int
    needs_enrichment_count: int
    ready_for_scoring_count: int
    candidate_record_ids: list[int] = Field(default_factory=list)
    candidate_row_ids: list[str] = Field(default_factory=list)


class LotEnrichmentExecutionResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_count: int
    processed_count: int
    fetched_count: int
    cleared_count: int
    still_missing_count: int
    skipped_count: int
    candidate_record_ids: list[int] = Field(default_factory=list)


class LotTtlRefreshEvaluation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    needs_refresh: bool
    reason_category: str = "fresh_enough"
    stale_for_hours: int | None = None


class PriorityLotEnrichmentScheduleResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_count: int
    scheduled_count: int
    skipped_count: int
    candidate_record_ids: list[int] = Field(default_factory=list)
    scheduled_record_ids: list[int] = Field(default_factory=list)


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
DEADLINE_PATTERNS: tuple[str, ...] = (
    "%d.%m.%Y %H:%M:%S",
    "%d.%m.%Y %H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%Y-%m-%dT%H:%M:%S",
)
DEFAULT_ENRICHMENT_CANDIDATE_LIMIT = 50
DEFAULT_ENRICHMENT_CLAIM_SECONDS = 15 * 60
ENRICHMENT_BACKOFF_BASE_SECONDS = 30 * 60
ENRICHMENT_BACKOFF_MAX_SECONDS = 24 * 60 * 60
ENRICHMENT_MAX_ATTEMPTS = 3
ENRICHMENT_WORKER_ID = "auction-enrichment-worker"
TTL_REFRESH_HOURS = 7 * 24
TTL_REFRESH_HIGH_SCORE_THRESHOLD = 75
TTL_REFRESH_NEAR_DEADLINE_HOURS = 48
PRIORITY_REFRESH_TOP_30_TTL_HOURS = 24
PRIORITY_REFRESH_TOP_100_TTL_HOURS = 72
PRIORITY_REFRESH_NEAR_DEADLINE_WINDOW_HOURS = 72
PRIORITY_REFRESH_NEAR_DEADLINE_SOON_TTL_HOURS = 12
PRIORITY_REFRESH_NEAR_DEADLINE_LATE_TTL_HOURS = 24
ENRICHMENT_PRIORITY_FAR_FUTURE = datetime(9999, 12, 31, 23, 59, 59, tzinfo=UTC)


def evaluate_lot_enrichment_requirements(evidence: LotEvidence) -> LotEnrichmentRequirementEvaluation:
    missing_fields: list[str] = []
    if not _has_price_facts(evidence):
        missing_fields.append("price")
    if not _has_location_facts(evidence):
        missing_fields.append("location")
    if not _has_category_facts(evidence):
        missing_fields.append("category")
    if not _has_deadline_facts(evidence):
        missing_fields.append("deadline")

    needs_enrichment = bool(missing_fields)
    return LotEnrichmentRequirementEvaluation(
        needs_enrichment=needs_enrichment,
        missing_fields=missing_fields,
        reason_category="missing_first_pass_evidence" if needs_enrichment else "ready_for_scoring",
    )


def classify_lot_enrichment(
    record: AuctionLotRecord,
    detail_cache: AuctionLotDetailCache | None = None,
) -> LotEnrichmentRequirementEvaluation:
    return evaluate_lot_enrichment_requirements(build_lot_evidence(record, detail_cache))


def evaluate_lot_ttl_refresh(
    record: AuctionLotRecord,
    detail_cache: AuctionLotDetailCache | None = None,
    *,
    current_time: datetime | None = None,
    ttl_hours: int = TTL_REFRESH_HOURS,
    high_score_threshold: int = TTL_REFRESH_HIGH_SCORE_THRESHOLD,
    near_deadline_hours: int = TTL_REFRESH_NEAR_DEADLINE_HOURS,
) -> LotTtlRefreshEvaluation:
    current_time = current_time or datetime.now(UTC)
    if detail_cache is None or detail_cache.fetched_at is None:
        return LotTtlRefreshEvaluation(needs_refresh=False, reason_category="no_detail_cache")
    if _is_terminal_status(record.status):
        return LotTtlRefreshEvaluation(needs_refresh=False, reason_category="terminal")

    evidence = build_lot_evidence(record, detail_cache)
    hours_to_deadline = evidence.deadlines.hours_to_deadline
    stale_for_hours = int((current_time - detail_cache.fetched_at).total_seconds() // 3600)
    if stale_for_hours < ttl_hours:
        return LotTtlRefreshEvaluation(
            needs_refresh=False,
            reason_category="ttl_not_expired",
            stale_for_hours=stale_for_hours,
        )

    high_value = int(getattr(record, "rating_score", 0) or 0) >= high_score_threshold
    time_sensitive = hours_to_deadline is not None and hours_to_deadline <= near_deadline_hours
    if not high_value and not time_sensitive:
        return LotTtlRefreshEvaluation(
            needs_refresh=False,
            reason_category="not_priority_enough",
            stale_for_hours=stale_for_hours,
        )

    return LotTtlRefreshEvaluation(
        needs_refresh=True,
        reason_category="ttl_expired",
        stale_for_hours=stale_for_hours,
    )


def schedule_lot_ttl_refresh(
    record: AuctionLotRecord,
    evaluation: LotTtlRefreshEvaluation,
    *,
    requested_at: datetime | None = None,
    force: bool = False,
) -> bool:
    if not evaluation.needs_refresh:
        return False
    if record.enrichment_requested_at is not None and not force:
        return False
    record.enrichment_requested_at = requested_at or datetime.now(UTC)
    return True


def build_lot_enrichment_candidate_statement(
    *,
    source_code: str | None = None,
    current_time: datetime | None = None,
    limit: int | None = 50,
):
    current_time = current_time or datetime.now(UTC)
    priority_order = _lot_enrichment_claim_priority_order()
    statement = (
        select(AuctionLotRecord)
        .join(AuctionSourceState, AuctionSourceState.code == AuctionLotRecord.source_code)
        .where(AuctionLotRecord.enrichment_requested_at.is_not(None))
        .where(
            or_(
                AuctionLotRecord.next_enrichment_attempt_at.is_(None),
                AuctionLotRecord.next_enrichment_attempt_at <= current_time,
            )
        )
        .where(
            or_(
                AuctionLotRecord.enrichment_claimed_at.is_(None),
                AuctionLotRecord.enrichment_claim_expires_at.is_(None),
                AuctionLotRecord.enrichment_claim_expires_at <= current_time,
            )
        )
        .where(AuctionLotRecord.enrichment_attempt_count < ENRICHMENT_MAX_ATTEMPTS)
        .where(AuctionSourceState.enabled.is_(True))
        .where(~_terminal_status_predicate())
        .order_by(*priority_order)
    )
    if source_code:
        statement = statement.where(AuctionLotRecord.source_code == source_code)
    if limit is not None:
        statement = statement.limit(max(0, limit))
    return statement


async def list_lot_enrichment_candidates(
    session: AsyncSession,
    *,
    source_code: str | None = None,
    current_time: datetime | None = None,
    limit: int = DEFAULT_ENRICHMENT_CANDIDATE_LIMIT,
) -> list[AuctionLotRecord]:
    current_time = current_time or datetime.now(UTC)
    statement = build_lot_enrichment_candidate_statement(source_code=source_code, current_time=current_time, limit=None)
    records = (await session.scalars(statement)).all()
    return collect_lot_enrichment_candidates(records, current_time=current_time, limit=limit)


def collect_lot_enrichment_candidates(
    records: Sequence[AuctionLotRecord],
    *,
    current_time: datetime | None = None,
    limit: int | None = DEFAULT_ENRICHMENT_CANDIDATE_LIMIT,
) -> list[AuctionLotRecord]:
    current_time = current_time or datetime.now(UTC)
    eligible = [record for record in records if _is_enrichment_candidate(record, current_time=current_time)]
    eligible.sort(key=lambda record: build_lot_enrichment_priority_key(record, current_time=current_time))
    if limit is None:
        return eligible
    if limit <= 0:
        return []
    return eligible[:limit]


def schedule_lot_enrichment(
    record: AuctionLotRecord,
    evaluation: LotEnrichmentRequirementEvaluation,
    *,
    requested_at: datetime | None = None,
    force: bool = False,
) -> bool:
    if evaluation.needs_enrichment:
        next_requested_at = requested_at or datetime.now(UTC)
        if not force and record.enrichment_requested_at is not None:
            return False
        record.enrichment_requested_at = next_requested_at
        return True
    if record.enrichment_requested_at is None and record.next_enrichment_attempt_at is None and not record.last_enrichment_error:
        return False
    record.enrichment_requested_at = None
    record.next_enrichment_attempt_at = None
    record.last_enrichment_error = None
    return True


async def dry_run_lot_enrichment_candidates(
    session: AsyncSession,
    *,
    source_code: str | None = None,
    limit: int = DEFAULT_ENRICHMENT_CANDIDATE_LIMIT,
) -> LotEnrichmentDryRunResult:
    now = datetime.now(UTC)
    candidates = await list_lot_enrichment_candidates(session, source_code=source_code, current_time=now, limit=limit)
    evaluations = [classify_lot_enrichment(record) for record in candidates]
    needs_enrichment_count = sum(1 for evaluation in evaluations if evaluation.needs_enrichment)
    candidate_record_ids = [record.id for record in candidates if record.id is not None]
    candidate_row_ids = [record.datagrid_row.get("row_id") for record in candidates if isinstance(record.datagrid_row, dict)]
    return LotEnrichmentDryRunResult(
        candidate_count=len(candidates),
        processed_count=len(candidates),
        needs_enrichment_count=needs_enrichment_count,
        ready_for_scoring_count=len(candidates) - needs_enrichment_count,
        candidate_record_ids=candidate_record_ids,
        candidate_row_ids=[row_id for row_id in candidate_row_ids if isinstance(row_id, str) and row_id],
    )


async def schedule_priority_lot_enrichment(
    session: AsyncSession,
    *,
    current_time: datetime | None = None,
) -> PriorityLotEnrichmentScheduleResult:
    current_time = current_time or datetime.now(UTC)
    top_ranked_records = await _list_priority_refresh_records(
        session,
        current_time=current_time,
        limit=100,
        order_by_deadline=False,
    )
    deadline_records = await _list_priority_refresh_records(
        session,
        current_time=current_time,
        limit=None,
        order_by_deadline=True,
    )

    candidate_records: list[AuctionLotRecord] = []
    seen_record_ids: set[int] = set()
    for record in top_ranked_records + deadline_records:
        record_id = getattr(record, "id", None)
        if record_id is None or record_id in seen_record_ids:
            continue
        seen_record_ids.add(record_id)
        candidate_records.append(record)
    top_ranked_record_ids = {record.id for record in top_ranked_records if record.id is not None}

    detail_cache_map = await _load_detail_caches_by_record_id(session, candidate_records)
    scheduled_count = 0
    skipped_count = 0
    scheduled_record_ids: list[int] = []

    for rank, record in enumerate(top_ranked_records, start=1):
        detail_cache = detail_cache_map.get(record.id)
        ttl_hours = _priority_refresh_ttl_hours(record, current_time=current_time, rank=rank)
        if ttl_hours is None:
            continue
        if _priority_refresh_is_blocked(record, current_time=current_time):
            skipped_count += 1
            continue
        if not _priority_refresh_needs_schedule(record, detail_cache, current_time=current_time, ttl_hours=ttl_hours):
            continue
        if schedule_lot_ttl_refresh(
            record,
            LotTtlRefreshEvaluation(
                needs_refresh=True,
                reason_category="priority_ttl_expired",
                stale_for_hours=_priority_refresh_stale_for_hours(detail_cache, current_time=current_time),
            ),
            requested_at=current_time,
        ):
            scheduled_count += 1
            scheduled_record_ids.append(record.id)

    deadline_only_records = [record for record in candidate_records if record.id not in top_ranked_record_ids]
    for record in deadline_only_records:
        detail_cache = detail_cache_map.get(record.id)
        ttl_hours = _priority_refresh_ttl_hours(record, current_time=current_time, rank=None)
        if ttl_hours is None:
            continue
        if _priority_refresh_is_blocked(record, current_time=current_time):
            skipped_count += 1
            continue
        if not _priority_refresh_needs_schedule(record, detail_cache, current_time=current_time, ttl_hours=ttl_hours):
            continue
        if schedule_lot_ttl_refresh(
            record,
            LotTtlRefreshEvaluation(
                needs_refresh=True,
                reason_category="priority_ttl_expired",
                stale_for_hours=_priority_refresh_stale_for_hours(detail_cache, current_time=current_time),
            ),
            requested_at=current_time,
        ):
            scheduled_count += 1
            scheduled_record_ids.append(record.id)

    await session.flush()
    return PriorityLotEnrichmentScheduleResult(
        candidate_count=len(candidate_records),
        scheduled_count=scheduled_count,
        skipped_count=skipped_count,
        candidate_record_ids=[record.id for record in candidate_records if record.id is not None],
        scheduled_record_ids=scheduled_record_ids,
    )


async def execute_lot_enrichment_candidates(
    session: AsyncSession,
    *,
    source_code: str | None = None,
    limit: int = DEFAULT_ENRICHMENT_CANDIDATE_LIMIT,
    item_pause_seconds: float = 0.0,
) -> LotEnrichmentExecutionResult:
    now = datetime.now(UTC)
    candidates = await claim_lot_enrichment_candidates(
        session,
        source_code=source_code,
        current_time=now,
        limit=limit,
    )
    processed_count = 0
    fetched_count = 0
    cleared_count = 0
    still_missing_count = 0
    skipped_count = 0
    candidate_record_ids: list[int] = []

    for record in candidates:
        processed_count += 1
        if record.id is None:
            skipped_count += 1
            if item_pause_seconds > 0:
                await asyncio.sleep(item_pause_seconds)
            continue
        candidate_record_ids.append(record.id)
        evaluation_before = classify_lot_enrichment(record)
        if not evaluation_before.needs_enrichment:
            if schedule_lot_enrichment(record, evaluation_before):
                cleared_count += 1
            else:
                skipped_count += 1
            _release_lot_enrichment_claim(record)
            if item_pause_seconds > 0:
                await asyncio.sleep(item_pause_seconds)
            continue

        attempt_marked = _mark_enrichment_attempt(record, now=now)
        detail_cache_before = await session.scalar(
            select(AuctionLotDetailCache).where(AuctionLotDetailCache.lot_record_id == record.id)
        )
        fetched_at_before = detail_cache_before.fetched_at if detail_cache_before is not None else None
        detail_cache = await ensure_lot_detail_cache(session, record, refresh=True)
        fetched_count += 1
        evaluation_after = evaluate_lot_enrichment_requirements(build_lot_evidence(record, detail_cache))
        if evaluation_after.needs_enrichment:
            _schedule_lot_retry(
                record,
                now=now,
                reason=_enrichment_failure_reason(evaluation_after, detail_cache, fetched_at_before=fetched_at_before),
            )
            _release_lot_enrichment_claim(record)
            if not attempt_marked:
                skipped_count += 1
            still_missing_count += 1
            if item_pause_seconds > 0:
                await asyncio.sleep(item_pause_seconds)
            continue

        if schedule_lot_enrichment(record, evaluation_after):
            cleared_count += 1
        _release_lot_enrichment_claim(record)
        if item_pause_seconds > 0:
            await asyncio.sleep(item_pause_seconds)

    return LotEnrichmentExecutionResult(
        candidate_count=len(candidates),
        processed_count=processed_count,
        fetched_count=fetched_count,
        cleared_count=cleared_count,
        still_missing_count=still_missing_count,
        skipped_count=skipped_count,
        candidate_record_ids=candidate_record_ids,
    )


def _is_enrichment_candidate(record: AuctionLotRecord, *, current_time: datetime | None = None) -> bool:
    current_time = current_time or datetime.now(UTC)
    next_retry = getattr(record, "next_enrichment_attempt_at", None)
    claim_expires_at = getattr(record, "enrichment_claim_expires_at", None)
    return (
        record.enrichment_requested_at is not None
        and (next_retry is None or next_retry <= current_time)
        and not _is_enrichment_maxed_out(record)
        and (
            getattr(record, "enrichment_claimed_at", None) is None
            or claim_expires_at is None
            or claim_expires_at <= current_time
        )
        and not _is_terminal_status(record.status)
    )


def _candidate_sort_key(record: AuctionLotRecord) -> tuple[object, ...]:
    return build_lot_enrichment_priority_key(record)


def build_lot_enrichment_priority_key(
    record: AuctionLotRecord,
    *,
    current_time: datetime | None = None,
) -> tuple[object, ...]:
    current_time = current_time or datetime.now(UTC)
    rating_score = int(getattr(record, "rating_score", 0) or 0)
    deadline_hours = _candidate_hours_to_deadline(record, current_time=current_time)
    deadline_bucket = 0 if deadline_hours is not None else 1
    deadline_value = deadline_hours if deadline_hours is not None else 0
    freshness_value = _freshness_priority_value(getattr(record, "last_seen_at", None))
    requested_at = getattr(record, "enrichment_requested_at", None) or datetime.min.replace(tzinfo=UTC)
    return (-rating_score, deadline_bucket, deadline_value, freshness_value, requested_at, record.id or 0)


def _terminal_status_predicate():
    status_text = func.lower(func.coalesce(AuctionLotRecord.status, ""))
    return or_(*(status_text.contains(marker) for marker in TERMINAL_LOT_STATUS_MARKERS))


def _lot_enrichment_claim_priority_order() -> tuple[object, ...]:
    deadline_expression = func.least(
        func.coalesce(AuctionLotRecord.application_deadline_at, literal(ENRICHMENT_PRIORITY_FAR_FUTURE)),
        func.coalesce(AuctionLotRecord.auction_at, literal(ENRICHMENT_PRIORITY_FAR_FUTURE)),
    )
    return (
        AuctionLotRecord.rating_score.desc(),
        deadline_expression.asc(),
        AuctionLotRecord.last_seen_at.desc(),
        AuctionLotRecord.enrichment_requested_at.asc(),
        AuctionLotRecord.id.asc(),
    )


def _filter_lot_enrichment_candidates_in_order(
    records: Sequence[AuctionLotRecord],
    *,
    current_time: datetime | None = None,
    limit: int | None = DEFAULT_ENRICHMENT_CANDIDATE_LIMIT,
) -> list[AuctionLotRecord]:
    current_time = current_time or datetime.now(UTC)
    eligible = [record for record in records if _is_enrichment_candidate(record, current_time=current_time)]
    if limit is None:
        return eligible
    if limit <= 0:
        return []
    return eligible[:limit]


def _is_enrichment_maxed_out(record: AuctionLotRecord) -> bool:
    return int(getattr(record, "enrichment_attempt_count", 0) or 0) >= ENRICHMENT_MAX_ATTEMPTS


def _is_terminal_status(status: str | None) -> bool:
    if not isinstance(status, str):
        return False
    normalized = status.strip().lower()
    if not normalized:
        return False
    return any(marker in normalized for marker in TERMINAL_LOT_STATUS_MARKERS)


def _mark_enrichment_attempt(record: AuctionLotRecord, *, now: datetime) -> bool:
    record.last_enrichment_attempt_at = now
    record.enrichment_attempt_count = int(getattr(record, "enrichment_attempt_count", 0) or 0) + 1
    return True


def _schedule_lot_retry(record: AuctionLotRecord, *, now: datetime, reason: str | None) -> None:
    attempt_count = int(getattr(record, "enrichment_attempt_count", 0) or 0)
    record.last_enrichment_error = reason
    if attempt_count >= ENRICHMENT_MAX_ATTEMPTS:
        record.next_enrichment_attempt_at = None
        return
    record.next_enrichment_attempt_at = _next_enrichment_attempt_at(now, attempt_count=attempt_count)
    record.enrichment_requested_at = record.enrichment_requested_at or now


async def claim_lot_enrichment_candidates(
    session: AsyncSession,
    *,
    source_code: str | None = None,
    current_time: datetime | None = None,
    limit: int = DEFAULT_ENRICHMENT_CANDIDATE_LIMIT,
    worker_id: str = ENRICHMENT_WORKER_ID,
    lease_seconds: int = DEFAULT_ENRICHMENT_CLAIM_SECONDS,
) -> list[AuctionLotRecord]:
    current_time = current_time or datetime.now(UTC)
    statement = build_lot_enrichment_candidate_statement(source_code=source_code, current_time=current_time, limit=None)
    statement = statement.with_for_update(skip_locked=True, of=AuctionLotRecord)
    records = (await session.scalars(statement)).all()
    claimed = _filter_lot_enrichment_candidates_in_order(records, current_time=current_time, limit=limit)
    if not claimed:
        return []
    claim_expires_at = current_time + timedelta(seconds=max(1, lease_seconds))
    for record in claimed:
        record.enrichment_claimed_at = current_time
        record.enrichment_claimed_by = worker_id
        record.enrichment_claim_expires_at = claim_expires_at
    await session.flush()
    return claimed


def _enrichment_failure_reason(
    evaluation: LotEnrichmentRequirementEvaluation,
    detail_cache: AuctionLotDetailCache | None,
    *,
    fetched_at_before: datetime | None,
) -> str:
    if detail_cache is None:
        return "detail_refresh_failed"
    if fetched_at_before is not None and detail_cache.fetched_at == fetched_at_before:
        return "detail_refresh_failed"
    missing = ",".join(evaluation.missing_fields)
    return f"missing_first_pass_evidence:{missing}" if missing else "missing_first_pass_evidence"


def _next_enrichment_attempt_at(now: datetime, *, attempt_count: int) -> datetime:
    exponent = max(0, attempt_count - 1)
    delay_seconds = min(ENRICHMENT_BACKOFF_BASE_SECONDS * (2**exponent), ENRICHMENT_BACKOFF_MAX_SECONDS)
    return now + timedelta(seconds=delay_seconds)


def _release_lot_enrichment_claim(record: AuctionLotRecord) -> None:
    record.enrichment_claimed_at = None
    record.enrichment_claimed_by = None
    record.enrichment_claim_expires_at = None


def _candidate_hours_to_deadline(record: AuctionLotRecord, *, current_time: datetime) -> int | None:
    deadline_text = _candidate_deadline_text(record)
    if not deadline_text:
        return None
    deadline = _parse_deadline(deadline_text)
    if deadline is None:
        return None
    remaining_seconds = (deadline - current_time.replace(tzinfo=None)).total_seconds()
    return int(remaining_seconds // 3600)


def _candidate_deadline_text(record: AuctionLotRecord) -> str | None:
    row = record.datagrid_row if isinstance(record.datagrid_row, dict) else {}
    normalized_item = record.normalized_item if isinstance(record.normalized_item, dict) else {}
    normalized_auction = normalized_item.get("auction") if isinstance(normalized_item.get("auction"), dict) else {}
    normalized_lot = normalized_item.get("lot") if isinstance(normalized_item.get("lot"), dict) else {}
    return _first_text(
        row.get("application_deadline"),
        row.get("auction_date"),
        normalized_auction.get("application_deadline"),
        normalized_auction.get("auction_date"),
        normalized_lot.get("application_deadline"),
        normalized_lot.get("auction_date"),
    )


def _freshness_priority_value(last_seen_at: datetime | None) -> float:
    if last_seen_at is None:
        return float("inf")
    if last_seen_at.tzinfo is None:
        last_seen_at = last_seen_at.replace(tzinfo=UTC)
    return -last_seen_at.timestamp()


def _first_text(*values: object) -> str | None:
    for value in values:
        if isinstance(value, str):
            normalized = value.strip()
            if normalized:
                return normalized
    return None


def _parse_deadline(value: str) -> datetime | None:
    normalized = value.strip()
    for pattern in DEADLINE_PATTERNS:
        try:
            return datetime.strptime(normalized[:19], pattern)
        except ValueError:
            continue
    return None


async def _list_priority_refresh_records(
    session: AsyncSession,
    *,
    current_time: datetime,
    limit: int | None,
    order_by_deadline: bool,
) -> list[AuctionLotRecord]:
    statement = select(AuctionLotRecord).where(AuctionLotRecord.lifecycle_status == "active")
    if order_by_deadline:
        statement = statement.where(
            or_(
                _priority_deadline_within_window_statement(current_time),
                _priority_auction_within_window_statement(current_time),
            )
        ).order_by(
            AuctionLotRecord.application_deadline_at.asc().nulls_last(),
            AuctionLotRecord.auction_at.asc().nulls_last(),
            AuctionLotRecord.rating_score.desc(),
            AuctionLotRecord.id.asc(),
        )
    else:
        statement = statement.order_by(AuctionLotRecord.rating_score.desc(), AuctionLotRecord.id.asc())
    if limit is not None:
        statement = statement.limit(max(0, limit))
    return (await session.scalars(statement)).all()


async def _load_detail_caches_by_record_id(
    session: AsyncSession,
    records: Sequence[AuctionLotRecord],
) -> dict[int, AuctionLotDetailCache]:
    record_ids = [record.id for record in records if record.id is not None]
    if not record_ids:
        return {}
    statement = select(AuctionLotDetailCache).where(AuctionLotDetailCache.lot_record_id.in_(record_ids))
    detail_caches = (await session.scalars(statement)).all()
    return {detail_cache.lot_record_id: detail_cache for detail_cache in detail_caches}


def _priority_refresh_ttl_hours(
    record: AuctionLotRecord,
    *,
    current_time: datetime,
    rank: int | None,
) -> int | None:
    if rank is not None:
        if rank <= 30:
            ttl_hours = PRIORITY_REFRESH_TOP_30_TTL_HOURS
        elif rank <= 100:
            ttl_hours = PRIORITY_REFRESH_TOP_100_TTL_HOURS
        else:
            ttl_hours = None
    else:
        ttl_hours = None

    deadline_hours = _candidate_hours_to_deadline(record, current_time=current_time)
    if deadline_hours is None or deadline_hours > PRIORITY_REFRESH_NEAR_DEADLINE_WINDOW_HOURS:
        return ttl_hours

    deadline_ttl = (
        PRIORITY_REFRESH_NEAR_DEADLINE_SOON_TTL_HOURS
        if deadline_hours <= 24
        else PRIORITY_REFRESH_NEAR_DEADLINE_LATE_TTL_HOURS
    )
    if ttl_hours is None:
        return deadline_ttl
    return min(ttl_hours, deadline_ttl)


def _priority_refresh_needs_schedule(
    record: AuctionLotRecord,
    detail_cache: AuctionLotDetailCache | None,
    *,
    current_time: datetime,
    ttl_hours: int,
) -> bool:
    if record.enrichment_requested_at is not None:
        return False
    if detail_cache is None or detail_cache.fetched_at is None:
        return True
    stale_for_hours = int((current_time - detail_cache.fetched_at).total_seconds() // 3600)
    return stale_for_hours >= ttl_hours


def _priority_refresh_stale_for_hours(
    detail_cache: AuctionLotDetailCache | None,
    *,
    current_time: datetime,
) -> int | None:
    if detail_cache is None or detail_cache.fetched_at is None:
        return None
    return int((current_time - detail_cache.fetched_at).total_seconds() // 3600)


def _priority_refresh_is_blocked(record: AuctionLotRecord, *, current_time: datetime) -> bool:
    claim_expires_at = getattr(record, "enrichment_claim_expires_at", None)
    if getattr(record, "enrichment_claimed_at", None) is not None and (
        claim_expires_at is None or claim_expires_at > current_time
    ):
        return True
    next_retry = getattr(record, "next_enrichment_attempt_at", None)
    if next_retry is not None and next_retry > current_time:
        return True
    if _is_terminal_status(record.status):
        return True
    return False


def _priority_deadline_within_window_statement(current_time: datetime):
    window_end = current_time + timedelta(hours=PRIORITY_REFRESH_NEAR_DEADLINE_WINDOW_HOURS)
    return and_(
        AuctionLotRecord.application_deadline_at.is_not(None),
        AuctionLotRecord.application_deadline_at <= window_end,
    )


def _priority_auction_within_window_statement(current_time: datetime):
    window_end = current_time + timedelta(hours=PRIORITY_REFRESH_NEAR_DEADLINE_WINDOW_HOURS)
    return and_(
        AuctionLotRecord.auction_at.is_not(None),
        AuctionLotRecord.auction_at <= window_end,
    )


def _has_price_facts(evidence: LotEvidence) -> bool:
    return any(
        [
            evidence.price.current_price is not None,
            evidence.price.initial_price is not None,
            evidence.price.minimum_price is not None,
            evidence.price.market_value is not None,
        ]
    )


def _has_location_facts(evidence: LotEvidence) -> bool:
    return any(
        [
            _has_text(evidence.location.region),
            _has_text(evidence.location.city),
            _has_text(evidence.location.address),
            _has_text(evidence.location.coordinates),
        ]
    )


def _has_category_facts(evidence: LotEvidence) -> bool:
    return any(
        [
            _has_text(evidence.category.category),
            _has_text(evidence.category.model_category),
        ]
    )


def _has_deadline_facts(evidence: LotEvidence) -> bool:
    return any(
        [
            _has_text(evidence.deadlines.application_deadline),
            _has_text(evidence.deadlines.auction_date),
            _has_text(evidence.deadlines.application_start),
            evidence.deadlines.hours_to_deadline is not None,
        ]
    )


def _has_text(value: str | None) -> bool:
    return isinstance(value, str) and bool(value.strip())
