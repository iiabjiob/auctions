from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Mapping

from app.models.auction import AuctionLotAiAnalysis, AuctionLotDetailCache, AuctionLotRecord, AuctionLotWorkItem
from app.services.auction_datagrid_payload import validate_datagrid_row_payload


AI_SHORTLIST_MIN_DETERMINISTIC_SCORE = 85
AI_SHORTLIST_DECISIONS = {"watch", "calculate", "inspection", "bid"}
AI_FEEDBACK_STATUSES = {"accepted", "rejected", "needs_review"}


@dataclass(frozen=True)
class AiCandidate:
    lot_record_id: int
    deterministic_score: int
    deterministic_rank: int
    payload: dict[str, Any]


def is_deterministic_ai_candidate(
    record: AuctionLotRecord,
    work_item: AuctionLotWorkItem | None = None,
    *,
    min_score: int = AI_SHORTLIST_MIN_DETERMINISTIC_SCORE,
) -> bool:
    if record.rating_score >= min_score:
        return True
    decision = (work_item.decision_status or "").strip().lower() if work_item else ""
    return decision in AI_SHORTLIST_DECISIONS


def build_ai_candidate_payload(
    record: AuctionLotRecord,
    detail_cache: AuctionLotDetailCache | None = None,
    work_item: AuctionLotWorkItem | None = None,
) -> dict[str, Any]:
    row = validate_datagrid_row_payload(record.datagrid_row)
    return {
        "lot_record_id": record.id,
        "source_code": record.source_code,
        "auction_external_id": record.auction_external_id,
        "lot_external_id": record.lot_external_id,
        "auction_number": record.auction_number,
        "lot_number": record.lot_number,
        "lot_name": record.lot_name,
        "status": record.status,
        "deterministic_score": record.rating_score,
        "deterministic_level": record.rating_level,
        "deterministic_scoring_version": record.scoring_version,
        "score_breakdown": record.score_breakdown,
        "analysis": row.analysis.model_dump(mode="json"),
        "economy": _json_payload({
            "current_price": row.current_price_value,
            "market_value": row.market_value,
            "full_entry_cost": row.full_entry_cost,
            "potential_profit": row.potential_profit,
            "roi": row.roi,
            "market_discount": row.market_discount,
        }),
        "work_item": {
            "decision_status": work_item.decision_status if work_item else None,
            "final_decision": work_item.final_decision if work_item else None,
            "comment": work_item.comment if work_item else None,
            "inspection_result": work_item.inspection_result if work_item else None,
        },
        "detail_summary": {
            "has_detail_cache": detail_cache is not None,
            "document_count": len(detail_cache.documents) if detail_cache else 0,
            "content_hash": detail_cache.content_hash if detail_cache else None,
        },
    }


def build_ai_candidates(
    records: list[AuctionLotRecord],
    *,
    detail_caches: Mapping[int, AuctionLotDetailCache] | None = None,
    work_items: Mapping[int, AuctionLotWorkItem] | None = None,
    min_score: int = AI_SHORTLIST_MIN_DETERMINISTIC_SCORE,
) -> list[AiCandidate]:
    detail_caches = detail_caches or {}
    work_items = work_items or {}
    sorted_records = sorted(records, key=lambda item: (-item.rating_score, item.id or 0))
    candidates: list[AiCandidate] = []
    for deterministic_rank, record in enumerate(sorted_records, start=1):
        work_item = work_items.get(record.id)
        if not is_deterministic_ai_candidate(record, work_item, min_score=min_score):
            continue
        candidates.append(
            AiCandidate(
                lot_record_id=record.id,
                deterministic_score=record.rating_score,
                deterministic_rank=deterministic_rank,
                payload=build_ai_candidate_payload(
                    record,
                    detail_cache=detail_caches.get(record.id),
                    work_item=work_item,
                ),
            )
        )
    return candidates


def create_ai_analysis_record(
    candidate: AiCandidate,
    *,
    model_version: str,
    prompt_version: str,
    ai_score: int | None,
    explanation: str | None,
    confidence: Decimal | None,
    output_payload: dict[str, Any] | None = None,
) -> AuctionLotAiAnalysis:
    return AuctionLotAiAnalysis(
        lot_record_id=candidate.lot_record_id,
        deterministic_scoring_version=str(candidate.payload["deterministic_scoring_version"]),
        deterministic_score=candidate.deterministic_score,
        deterministic_rank=candidate.deterministic_rank,
        ai_score=ai_score,
        model_version=model_version,
        prompt_version=prompt_version,
        explanation=explanation,
        confidence=confidence,
        input_payload=_json_payload(candidate.payload),
        output_payload=_json_payload(output_payload or {}),
    )


def apply_operator_feedback(
    analysis: AuctionLotAiAnalysis,
    *,
    status: str,
    comment: str | None = None,
    reviewer: str | None = None,
) -> AuctionLotAiAnalysis:
    normalized_status = status.strip().lower()
    if normalized_status not in AI_FEEDBACK_STATUSES:
        allowed = ", ".join(sorted(AI_FEEDBACK_STATUSES))
        raise ValueError(f"Unsupported AI feedback status '{status}'. Expected one of: {allowed}")
    analysis.operator_feedback_status = normalized_status
    analysis.operator_feedback_comment = comment
    analysis.operator_feedback_by = reviewer
    analysis.operator_feedback_at = datetime.now(UTC)
    return analysis


def compare_deterministic_and_ai_ranks(candidates: list[AiCandidate], ai_scores: Mapping[int | str, int]) -> list[dict[str, Any]]:
    deterministic_rows = [
        {
            "lot_record_id": candidate.lot_record_id,
            "deterministic_score": candidate.deterministic_score,
            "deterministic_rank": candidate.deterministic_rank,
            "ai_score": _ai_score_for_candidate(candidate, ai_scores),
        }
        for candidate in candidates
        if _ai_score_for_candidate(candidate, ai_scores) is not None
    ]
    ai_ranked = sorted(deterministic_rows, key=lambda item: (-int(item["ai_score"]), item["deterministic_rank"]))
    ai_ranks = {item["lot_record_id"]: rank for rank, item in enumerate(ai_ranked, start=1)}
    return [
        {
            **item,
            "ai_rank": ai_ranks[item["lot_record_id"]],
            "rank_delta": ai_ranks[item["lot_record_id"]] - item["deterministic_rank"],
        }
        for item in deterministic_rows
    ]


def _ai_score_for_candidate(candidate: AiCandidate, ai_scores: Mapping[int | str, int]) -> int | None:
    if candidate.lot_record_id in ai_scores:
        return int(ai_scores[candidate.lot_record_id])
    case_id = candidate.payload.get("case_id")
    if isinstance(case_id, str) and case_id in ai_scores:
        return int(ai_scores[case_id])
    return None


def _json_payload(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_payload(item) for item in value]
    return value
