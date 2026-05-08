from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.models.auction import AuctionLotDetailCache, AuctionLotRecord, AuctionLotWorkItem
from app.schemas.lot_decision_report import (
    ActionRecommendation,
    DecisionLevel,
    LotDecisionNextAction,
    LotDecisionReason,
    LotDecisionReport,
    LotDecisionRisk,
)
from app.schemas.scoring_profile import LotScoringProfile, build_lot_scoring_profile_hash
from app.schemas.scoring_profile_fit import LotProfileFitEvaluation
from app.services.auction_datagrid_payload import validate_datagrid_row_payload
from app.services.lot_evidence import build_lot_evidence
from app.services.scoring_profile_fit import evaluate_lot_profile_fit


NEAR_DEADLINE_HOURS = 72


def build_lot_decision_report(
    record: AuctionLotRecord,
    detail_cache: AuctionLotDetailCache | None = None,
    work_item: AuctionLotWorkItem | None = None,
    profile: LotScoringProfile | None = None,
) -> LotDecisionReport:
    row = validate_datagrid_row_payload(record.datagrid_row)
    evidence = build_lot_evidence(record, detail_cache)
    profile_fit = evaluate_lot_profile_fit(evidence, profile) if profile is not None else None
    profile_hash = build_lot_scoring_profile_hash(profile) if profile is not None else None
    reasons = _decision_reasons(record, profile_fit=profile_fit)
    near_deadline = _is_near_deadline(
        record.score_breakdown,
        evidence.deadlines.hours_to_deadline,
    )
    risks = _decision_risks(
        record,
        work_item,
        profile_fit=profile_fit,
        has_documents=evidence.legal.has_documents,
    )
    decision_level = _decision_level(
        record,
        work_item,
        profile_fit=profile_fit,
        near_deadline=near_deadline,
    )
    recommendation = _recommendation(
        decision_level,
        record,
        work_item,
        has_documents=evidence.legal.has_documents,
    )
    next_actions = _next_actions(
        decision_level,
        recommendation,
        work_item,
        has_documents=evidence.legal.has_documents,
        deadline=evidence.deadlines.application_deadline or row.application_deadline,
    )

    return LotDecisionReport(
        source=record.source_code,
        auction_id=record.auction_external_id,
        lot_id=record.lot_external_id,
        record_id=record.id,
        title=row.lot_name or record.lot_name,
        source_title=row.source_title,
        region=row.location_region or evidence.location.region or row.location,
        current_price=row.current_price or record.initial_price,
        deadline=evidence.deadlines.application_deadline or row.application_deadline,
        rating_score=record.rating_score,
        rating_level=record.rating_level,
        profile_hash=profile_hash,
        profile_fit_summary=_profile_fit_summary(profile_fit),
        decision_level=decision_level,
        recommendation=recommendation,
        reasons=tuple(reasons),
        risks=tuple(risks),
        next_actions=tuple(next_actions),
        generated_at=datetime.now(UTC),
    )


def _decision_level(
    record: AuctionLotRecord,
    work_item: AuctionLotWorkItem | None,
    *,
    profile_fit: LotProfileFitEvaluation | None,
    near_deadline: bool,
) -> DecisionLevel:
    decision = _manual_decision(work_item)
    final_decision = _manual_final_decision(work_item)
    has_profile_blockers = bool(profile_fit and profile_fit.blockers)
    is_excluded = bool(work_item and work_item.exclude_from_analysis)
    score = int(record.rating_score or 0)

    if is_excluded or decision == "reject" or final_decision in {"reject", "rejected", "no"}:
        return DecisionLevel.IGNORE
    if has_profile_blockers:
        return DecisionLevel.WATCH if score >= 70 else DecisionLevel.IGNORE
    if score < 45:
        return DecisionLevel.IGNORE
    if score < 70:
        return DecisionLevel.WATCH
    if decision == "bid" or final_decision in {"approve", "approved", "bid", "go"}:
        return DecisionLevel.BID_CANDIDATE
    if decision == "calculate":
        return DecisionLevel.CALCULATE
    if decision == "inspection":
        return DecisionLevel.INSPECT
    if score >= 85 and profile_fit is not None and profile_fit.matches_profile:
        return DecisionLevel.BID_CANDIDATE
    if near_deadline:
        return DecisionLevel.CALCULATE
    return DecisionLevel.INSPECT


def _recommendation(
    decision_level: DecisionLevel,
    record: AuctionLotRecord,
    work_item: AuctionLotWorkItem | None,
    *,
    has_documents: bool,
) -> ActionRecommendation:
    if decision_level == DecisionLevel.IGNORE:
        return ActionRecommendation.IGNORE
    if work_item and work_item.max_purchase_price is not None:
        return ActionRecommendation.PREPARE_BID
    if not has_documents and decision_level in {DecisionLevel.WATCH, DecisionLevel.INSPECT, DecisionLevel.CALCULATE}:
        return ActionRecommendation.REQUEST_DOCS
    if decision_level == DecisionLevel.WATCH:
        return ActionRecommendation.MONITOR
    if decision_level == DecisionLevel.INSPECT:
        return ActionRecommendation.INSPECT
    if decision_level == DecisionLevel.CALCULATE:
        return ActionRecommendation.CALCULATE_MAX_BID
    if record.rating_score >= 85:
        return ActionRecommendation.PREPARE_BID
    return ActionRecommendation.CALCULATE_MAX_BID


def _next_actions(
    decision_level: DecisionLevel,
    recommendation: ActionRecommendation,
    work_item: AuctionLotWorkItem | None,
    *,
    has_documents: bool,
    deadline: str | None,
) -> list[LotDecisionNextAction]:
    if decision_level == DecisionLevel.IGNORE:
        return [LotDecisionNextAction(action=ActionRecommendation.IGNORE, label="Ignore lot")]

    actions: list[LotDecisionNextAction] = []
    if not has_documents:
        actions.append(
            LotDecisionNextAction(
                action=ActionRecommendation.REQUEST_DOCS,
                label="Request documents",
            )
        )
    if decision_level in {DecisionLevel.INSPECT, DecisionLevel.CALCULATE, DecisionLevel.BID_CANDIDATE}:
        actions.append(
            LotDecisionNextAction(
                action=ActionRecommendation.INSPECT,
                label="Inspect lot",
                deadline=deadline,
            )
        )
    if decision_level in {DecisionLevel.CALCULATE, DecisionLevel.BID_CANDIDATE} or work_item is None:
        actions.append(
            LotDecisionNextAction(
                action=ActionRecommendation.CALCULATE_MAX_BID,
                label="Calculate max bid",
                deadline=deadline,
            )
        )
    if decision_level == DecisionLevel.BID_CANDIDATE and work_item and work_item.max_purchase_price is not None:
        actions.append(
            LotDecisionNextAction(
                action=ActionRecommendation.PREPARE_BID,
                label="Prepare bid",
                deadline=deadline,
            )
        )
    if not actions:
        actions.append(
            LotDecisionNextAction(
                action=ActionRecommendation.MONITOR,
                label="Monitor lot",
                deadline=deadline,
            )
        )

    if all(action.action != recommendation for action in actions):
        actions.insert(
            0,
            LotDecisionNextAction(
                action=recommendation,
                label=_recommendation_label(recommendation),
                deadline=deadline,
            ),
        )
    return actions


def _decision_reasons(
    record: AuctionLotRecord,
    *,
    profile_fit: LotProfileFitEvaluation | None,
) -> list[LotDecisionReason]:
    reasons: list[LotDecisionReason] = []
    for index, reason in enumerate(_score_reason_texts(record.score_breakdown), start=1):
        reasons.append(
            LotDecisionReason(
                code=f"score.reason.{index}",
                message=reason,
                source="score_breakdown",
            )
        )
        if len(reasons) >= 5:
            break
    if not reasons:
        reasons.append(
            LotDecisionReason(
                code="score.current",
                message=f"Current rating is {record.rating_score}/{record.rating_level}",
                source="record",
            )
        )
    if profile_fit is not None:
        if profile_fit.blockers:
            reasons.append(
                LotDecisionReason(
                    code="profile.blockers",
                    message="Profile blockers present",
                    source="profile_fit",
                )
            )
        elif profile_fit.matches_profile:
            reasons.append(
                LotDecisionReason(
                    code="profile.match",
                    message="Lot matches profile",
                    source="profile_fit",
                )
            )
    return reasons[:5]


def _decision_risks(
    record: AuctionLotRecord,
    work_item: AuctionLotWorkItem | None,
    *,
    profile_fit: LotProfileFitEvaluation | None,
    has_documents: bool,
) -> list[LotDecisionRisk]:
    risks: list[LotDecisionRisk] = []
    if work_item and work_item.exclude_from_analysis:
        risks.append(
            LotDecisionRisk(
                code="manual.excluded",
                message=work_item.exclusion_reason or "Lot is manually excluded from analysis",
                level="high",
            )
        )
    if not has_documents:
        risks.append(
            LotDecisionRisk(
                code="documents.missing",
                message="Documents are not available in local data",
                level="medium",
            )
        )
    for cap in _score_caps(record.score_breakdown):
        risks.append(
            LotDecisionRisk(
                code=f"score.cap.{cap.get('key') or 'unknown'}",
                message=str(cap.get("reason") or cap.get("label") or "Score cap applied"),
                level="high" if int(cap.get("max_score") or 100) <= 44 else "medium",
            )
        )
        if len(risks) >= 5:
            return risks
    if profile_fit is not None:
        for blocker in profile_fit.blockers:
            risks.append(LotDecisionRisk(code="profile.blocker", message=blocker, level="high"))
            if len(risks) >= 5:
                return risks
    return risks


def _profile_fit_summary(profile_fit: LotProfileFitEvaluation | None) -> str | None:
    if profile_fit is None:
        return None
    if profile_fit.blockers:
        return "; ".join(profile_fit.blockers[:3])
    if profile_fit.reasons:
        return "; ".join(profile_fit.reasons[:3])
    return "Profile match" if profile_fit.matches_profile else "Profile does not match"


def _score_reason_texts(score_breakdown: dict[str, Any] | None) -> list[str]:
    if not isinstance(score_breakdown, dict):
        return []
    reasons = score_breakdown.get("reasons")
    if not isinstance(reasons, list):
        return []
    return [reason.strip() for reason in reasons if isinstance(reason, str) and reason.strip()]


def _score_caps(score_breakdown: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(score_breakdown, dict):
        return []
    caps = score_breakdown.get("caps")
    return [cap for cap in caps if isinstance(cap, dict)] if isinstance(caps, list) else []


def _is_near_deadline(
    score_breakdown: dict[str, Any] | None,
    hours_to_deadline: int | None,
) -> bool:
    if hours_to_deadline is not None:
        return 0 <= hours_to_deadline <= NEAR_DEADLINE_HOURS
    for reason in _score_reason_texts(score_breakdown):
        if "48" in reason or "deadline" in reason.casefold() or "дедлайн" in reason.casefold():
            return True
    inputs = score_breakdown.get("inputs") if isinstance(score_breakdown, dict) else None
    if not isinstance(inputs, dict):
        return False
    hours = inputs.get("hours_to_deadline")
    return isinstance(hours, int) and 0 <= hours <= NEAR_DEADLINE_HOURS


def _manual_decision(work_item: AuctionLotWorkItem | None) -> str:
    return (work_item.decision_status or "").strip().lower() if work_item else ""


def _manual_final_decision(work_item: AuctionLotWorkItem | None) -> str:
    return (work_item.final_decision or "").strip().lower() if work_item and work_item.final_decision else ""


def _recommendation_label(recommendation: ActionRecommendation) -> str:
    return {
        ActionRecommendation.IGNORE: "Ignore lot",
        ActionRecommendation.MONITOR: "Monitor lot",
        ActionRecommendation.REQUEST_DOCS: "Request documents",
        ActionRecommendation.INSPECT: "Inspect lot",
        ActionRecommendation.CALCULATE_MAX_BID: "Calculate max bid",
        ActionRecommendation.PREPARE_BID: "Prepare bid",
    }[recommendation]
