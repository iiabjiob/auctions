from __future__ import annotations

import hashlib
import json
from html import escape
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auction import (
    AuctionLotDecisionReport,
    AuctionLotDetailCache,
    AuctionLotRecord,
    AuctionLotWorkItem,
    TelegramNotificationOutbox,
)
from app.models.user_interest_profile import UserInterestProfileModel
from app.schemas.lot_decision_report import (
    ActionRecommendation,
    DecisionLevel,
    LotEconomicsDecision,
    LotDecisionNextAction,
    LotDecisionReason,
    LotDecisionReport,
    LotDecisionRisk,
    LotNotificationEligibility,
    TelegramNotificationStatus,
    TelegramLotMessage,
)
from app.schemas.scoring_profile import LotScoringProfile, build_lot_scoring_profile_hash
from app.schemas.scoring_profile_fit import LotProfileFitEvaluation
from app.services.auction_datagrid_payload import validate_datagrid_row_payload
from app.services.lot_evidence import build_lot_evidence
from app.services.scoring_profile_fit import evaluate_lot_profile_fit
from app.services.user_interest_matching import (
    build_lot_scoring_profile_from_interest,
    evaluate_user_interest_match,
)


NEAR_DEADLINE_HOURS = 72
NOTIFICATION_NEAR_DEADLINE_HOURS = 72
NOTIFICATION_HIGH_SCORE = 85
DEFAULT_TARGET_ROI = Decimal("0.25")
ECONOMICS_COST_FIELDS = (
    "platform_fee",
    "delivery_cost",
    "dismantling_cost",
    "repair_cost",
    "storage_cost",
    "legal_cost",
    "other_costs",
)
TELEGRAM_MAX_MESSAGE_LENGTH = 4096
TELEGRAM_REASON_LIMIT = 3
TELEGRAM_RISK_LIMIT = 2
TELEGRAM_NOTIFICATION_COOLDOWN_SECONDS = 6 * 60 * 60


def build_lot_decision_report(
    record: AuctionLotRecord,
    detail_cache: AuctionLotDetailCache | None = None,
    work_item: AuctionLotWorkItem | None = None,
    profile: LotScoringProfile | None = None,
) -> LotDecisionReport:
    row = validate_datagrid_row_payload(record.datagrid_row)
    evidence = build_lot_evidence(record, detail_cache)
    economics = calculate_lot_economics_decision(
        record,
        detail_cache=detail_cache,
        work_item=work_item,
        profile=profile,
    )
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
        current_status=evidence.category.status,
    )
    decision_level = _decision_level(
        record,
        work_item,
        profile_fit=profile_fit,
        near_deadline=near_deadline,
        current_status=evidence.category.status,
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
        economics=economics,
        decision_level=decision_level,
        recommendation=recommendation,
        reasons=tuple(reasons),
        risks=tuple(risks),
        next_actions=tuple(next_actions),
        generated_at=datetime.now(UTC),
    )


def calculate_lot_economics_decision(
    record: AuctionLotRecord,
    detail_cache: AuctionLotDetailCache | None = None,
    work_item: AuctionLotWorkItem | None = None,
    profile: LotScoringProfile | None = None,
    *,
    target_roi: Decimal | None = None,
) -> LotEconomicsDecision:
    row = validate_datagrid_row_payload(record.datagrid_row)
    evidence = build_lot_evidence(record, detail_cache)
    current_price = evidence.price.current_price or row.current_price_value or evidence.price.initial_price
    market_value = _first_decimal(
        _work_item_decimal(work_item, "market_value"),
        row.market_value,
        evidence.price.market_value,
    )
    expected_costs, has_cost_inputs = _expected_costs(work_item, row)
    resolved_target_roi = _resolve_target_roi(profile=profile, target_roi=target_roi)
    missing_inputs = _economics_missing_inputs(
        current_price=current_price,
        market_value=market_value,
        has_cost_inputs=has_cost_inputs,
    )

    if market_value is None:
        return LotEconomicsDecision(
            current_price=current_price,
            market_value=None,
            expected_costs=expected_costs,
            target_roi=resolved_target_roi,
            max_buy_price=None,
            estimated_profit=None,
            confidence="low",
            missing_inputs=tuple(missing_inputs),
        )

    max_buy_price = (market_value - expected_costs) / (Decimal("1") + resolved_target_roi)
    if max_buy_price < 0:
        max_buy_price = Decimal("0")
    estimated_profit = market_value - expected_costs - current_price if current_price is not None else None
    confidence = "high" if current_price is not None and has_cost_inputs else "medium"

    return LotEconomicsDecision(
        current_price=current_price,
        market_value=market_value,
        expected_costs=expected_costs,
        target_roi=resolved_target_roi,
        max_buy_price=max_buy_price,
        estimated_profit=estimated_profit,
        confidence=confidence,
        missing_inputs=tuple(missing_inputs),
    )


def evaluate_lot_notification_eligibility(
    report: LotDecisionReport,
    profile: LotScoringProfile | None = None,
) -> LotNotificationEligibility:
    profile_hash = report.profile_hash
    if profile_hash is None and profile is not None:
        profile_hash = build_lot_scoring_profile_hash(profile)

    blockers = _notification_blockers(report)
    reasons = _notification_reasons(report)
    priority = _notification_priority(report, blocked=bool(blockers))
    should_notify = not blockers and bool(reasons) and priority != "low"

    return LotNotificationEligibility(
        should_notify=should_notify,
        priority=priority if should_notify else "low",
        reasons=tuple(reasons if should_notify else ()),
        blockers=tuple(blockers),
        dedupe_key=_notification_dedupe_key(report, profile_hash=profile_hash),
        cooldown_key=_notification_cooldown_key(report, profile_hash=profile_hash),
    )


def build_lot_decision_report_snapshot_hash(report: LotDecisionReport) -> str:
    payload = report.model_dump(mode="json", exclude_none=True, exclude={"generated_at"})
    return _stable_hash(payload)


def render_telegram_lot_message(
    report: LotDecisionReport,
    *,
    link: str | None = None,
    max_length: int = TELEGRAM_MAX_MESSAGE_LENGTH,
) -> TelegramLotMessage:
    message_link = link or _default_lot_link(report)
    lines = [
        f"<b>{_html(report.title or 'Отчет по лоту')}</b>",
        _field_line("Регион", report.region),
        _field_line("Цена", report.current_price),
        f"Рейтинг: {report.rating_score} ({_html(report.rating_level)})",
        f"Решение: {_html(_decision_level_label(report.decision_level))} / {_html(_recommendation_label(report.recommendation))}",
        _field_line("Макс. цена", _format_decimal(report.economics.max_buy_price) if report.economics else None),
        _field_line("Дедлайн", report.deadline),
    ]
    reason_lines = _message_items("Причины", [reason.message for reason in report.reasons], TELEGRAM_REASON_LIMIT)
    risk_lines = _message_items("Риски", [risk.message for risk in report.risks], TELEGRAM_RISK_LIMIT)
    if reason_lines:
        lines.extend(reason_lines)
    if risk_lines:
        lines.extend(risk_lines)
    if message_link:
        lines.append(f"Ссылка: {_html(message_link)}")

    text = _trim_message("\n".join(line for line in lines if line), max_length=max_length)
    return TelegramLotMessage(
        text=text,
        lot_record_id=report.record_id,
        source=report.source,
        auction_id=report.auction_id,
        lot_id=report.lot_id,
        decision_level=report.decision_level,
        recommendation=report.recommendation,
        message_length=len(text),
    )


async def upsert_lot_decision_report_snapshot(
    session: AsyncSession,
    report: LotDecisionReport,
) -> AuctionLotDecisionReport:
    profile_hash = report.profile_hash
    statement = select(AuctionLotDecisionReport).where(
        AuctionLotDecisionReport.lot_record_id == report.record_id,
    )
    if profile_hash is None:
        statement = statement.where(AuctionLotDecisionReport.profile_hash.is_(None))
    else:
        statement = statement.where(AuctionLotDecisionReport.profile_hash == profile_hash)

    existing = await session.scalar(statement)
    payload = report.model_dump(mode="json")
    eligibility = evaluate_lot_notification_eligibility(report)
    report_hash = build_lot_decision_report_snapshot_hash(report)
    values = {
        "lot_record_id": report.record_id,
        "profile_hash": profile_hash,
        "report_payload": payload,
        "decision_level": report.decision_level.value,
        "recommendation": report.recommendation.value,
        "notification_should_send": eligibility.should_notify,
        "report_hash": report_hash,
        "generated_at": report.generated_at,
        "updated_at": datetime.now(UTC),
    }

    if existing is None:
        snapshot = AuctionLotDecisionReport(created_at=datetime.now(UTC), **values)
        session.add(snapshot)
        await session.flush()
        return snapshot

    for field, value in values.items():
        setattr(existing, field, value)
    await session.flush()
    return existing


async def enqueue_lot_telegram_notification_outbox(
    session: AsyncSession,
    snapshot: AuctionLotDecisionReport,
    *,
    report: LotDecisionReport | None = None,
    profile: LotScoringProfile | None = None,
    now: datetime | None = None,
    cooldown_seconds: int = TELEGRAM_NOTIFICATION_COOLDOWN_SECONDS,
) -> TelegramNotificationOutbox | None:
    decision_report_id = getattr(snapshot, "id", None)
    if decision_report_id is None:
        return None

    resolved_report = report or LotDecisionReport.model_validate(snapshot.report_payload)
    eligibility = evaluate_lot_notification_eligibility(resolved_report, profile=profile)
    if not eligibility.should_notify:
        return None

    existing = await session.scalar(
        select(TelegramNotificationOutbox).where(
            TelegramNotificationOutbox.dedupe_key == eligibility.dedupe_key,
        )
    )
    if existing is not None:
        return existing

    current_time = now or datetime.now(UTC)
    active_cooldown = await session.scalar(
        select(TelegramNotificationOutbox)
        .where(TelegramNotificationOutbox.cooldown_key == eligibility.cooldown_key)
        .where(TelegramNotificationOutbox.status.in_(_cooldown_blocking_statuses()))
        .where(TelegramNotificationOutbox.cooldown_until.is_not(None))
        .where(TelegramNotificationOutbox.cooldown_until > current_time)
        .order_by(TelegramNotificationOutbox.cooldown_until.desc())
        .limit(1)
    )
    status = (
        TelegramNotificationStatus.SKIPPED.value
        if active_cooldown is not None
        else TelegramNotificationStatus.PENDING.value
    )
    cooldown_until = (
        active_cooldown.cooldown_until
        if active_cooldown is not None
        else current_time + timedelta(seconds=cooldown_seconds)
    )
    message = render_telegram_lot_message(resolved_report)
    entry = TelegramNotificationOutbox(
        lot_record_id=resolved_report.record_id,
        decision_report_id=decision_report_id,
        dedupe_key=eligibility.dedupe_key,
        cooldown_key=eligibility.cooldown_key,
        status=status,
        priority=eligibility.priority,
        message_payload=message.model_dump(mode="json"),
        report_hash=snapshot.report_hash,
        scheduled_at=current_time,
        cooldown_until=cooldown_until,
        created_at=current_time,
        updated_at=current_time,
    )
    session.add(entry)
    await session.flush()
    return entry


async def enqueue_user_scoped_lot_telegram_notifications(
    session: AsyncSession,
    snapshot: AuctionLotDecisionReport,
    record: AuctionLotRecord,
    *,
    detail_cache: AuctionLotDetailCache | None = None,
    work_item: AuctionLotWorkItem | None = None,
    report: LotDecisionReport | None = None,
    now: datetime | None = None,
    cooldown_seconds: int = TELEGRAM_NOTIFICATION_COOLDOWN_SECONDS,
) -> list[TelegramNotificationOutbox]:
    decision_report_id = getattr(snapshot, "id", None)
    if decision_report_id is None:
        return []

    resolved_report = report or LotDecisionReport.model_validate(snapshot.report_payload)
    current_time = now or datetime.now(UTC)
    profiles = await _active_telegram_interest_profiles(session)
    entries: list[TelegramNotificationOutbox] = []
    added_entries = 0

    for interest_profile in profiles:
        match = evaluate_user_interest_match(
            record,
            interest_profile,
            detail_cache=detail_cache,
            work_item=work_item,
            report=resolved_report,
        )
        if not match.matches:
            continue

        scoring_profile = build_lot_scoring_profile_from_interest(interest_profile)
        profile_report = resolved_report.model_copy(
            update={
                "profile_hash": match.profile_hash,
                "profile_fit_summary": "; ".join(match.reasons[:3]) or None,
            }
        )
        eligibility = evaluate_lot_notification_eligibility(profile_report, profile=scoring_profile)
        if not eligibility.should_notify:
            continue

        dedupe_key = _user_notification_dedupe_key(
            user_id=interest_profile.owner_user_id,
            interest_profile_id=interest_profile.id,
            lot_record_id=resolved_report.record_id,
            report_hash=snapshot.report_hash,
        )
        existing = await session.scalar(
            select(TelegramNotificationOutbox).where(
                TelegramNotificationOutbox.dedupe_key == dedupe_key,
            )
        )
        if existing is not None:
            entries.append(existing)
            continue

        cooldown_key = _user_notification_cooldown_key(
            user_id=interest_profile.owner_user_id,
            interest_profile_id=interest_profile.id,
            lot_record_id=resolved_report.record_id,
        )
        active_cooldown = await session.scalar(
            select(TelegramNotificationOutbox)
            .where(TelegramNotificationOutbox.cooldown_key == cooldown_key)
            .where(TelegramNotificationOutbox.status.in_(_cooldown_blocking_statuses()))
            .where(TelegramNotificationOutbox.cooldown_until.is_not(None))
            .where(TelegramNotificationOutbox.cooldown_until > current_time)
            .order_by(TelegramNotificationOutbox.cooldown_until.desc())
            .limit(1)
        )
        status = (
            TelegramNotificationStatus.SKIPPED.value
            if active_cooldown is not None
            else TelegramNotificationStatus.PENDING.value
        )
        cooldown_until = (
            active_cooldown.cooldown_until
            if active_cooldown is not None
            else current_time + timedelta(seconds=cooldown_seconds)
        )
        message = render_telegram_lot_message(profile_report)
        entry = TelegramNotificationOutbox(
            lot_record_id=resolved_report.record_id,
            decision_report_id=decision_report_id,
            user_id=interest_profile.owner_user_id,
            telegram_chat_id=None,
            interest_profile_id=interest_profile.id,
            dedupe_key=dedupe_key,
            cooldown_key=cooldown_key,
            status=status,
            priority=eligibility.priority,
            message_payload=message.model_dump(mode="json"),
            report_hash=snapshot.report_hash,
            scheduled_at=current_time,
            cooldown_until=cooldown_until,
            created_at=current_time,
            updated_at=current_time,
        )
        session.add(entry)
        entries.append(entry)
        added_entries += 1

    if added_entries:
        await session.flush()
    return entries


async def generate_and_persist_lot_decision_report_snapshot(
    session: AsyncSession,
    record: AuctionLotRecord,
    detail_cache: AuctionLotDetailCache | None = None,
    work_item: AuctionLotWorkItem | None = None,
    profile: LotScoringProfile | None = None,
) -> AuctionLotDecisionReport | None:
    if not hasattr(session, "add") or not hasattr(session, "flush"):
        return None
    if getattr(record, "rating_score", None) is None or getattr(record, "rating_level", None) is None:
        return None
    report = build_lot_decision_report(
        record,
        detail_cache=detail_cache,
        work_item=work_item,
        profile=profile,
    )
    snapshot = await upsert_lot_decision_report_snapshot(session, report)
    await enqueue_lot_telegram_notification_outbox(session, snapshot, report=report, profile=profile)
    await enqueue_user_scoped_lot_telegram_notifications(
        session,
        snapshot,
        record,
        detail_cache=detail_cache,
        work_item=work_item,
        report=report,
    )
    return snapshot


def _decision_level(
    record: AuctionLotRecord,
    work_item: AuctionLotWorkItem | None,
    *,
    profile_fit: LotProfileFitEvaluation | None,
    near_deadline: bool,
    current_status: str | None,
) -> DecisionLevel:
    decision = _manual_decision(work_item)
    final_decision = _manual_final_decision(work_item)
    has_profile_blockers = bool(profile_fit and profile_fit.blockers)
    is_excluded = bool(work_item and getattr(work_item, "exclude_from_analysis", False))
    score = int(record.rating_score or 0)

    if _is_terminal_lot_status(current_status):
        return DecisionLevel.IGNORE
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
    if work_item and getattr(work_item, "max_purchase_price", None) is not None:
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
        return [LotDecisionNextAction(action=ActionRecommendation.IGNORE, label="Игнорировать лот")]

    actions: list[LotDecisionNextAction] = []
    if not has_documents:
        actions.append(
            LotDecisionNextAction(
                action=ActionRecommendation.REQUEST_DOCS,
                label="Запросить документы",
            )
        )
    if decision_level in {DecisionLevel.INSPECT, DecisionLevel.CALCULATE, DecisionLevel.BID_CANDIDATE}:
        actions.append(
            LotDecisionNextAction(
                action=ActionRecommendation.INSPECT,
                label="Осмотреть лот",
                deadline=deadline,
            )
        )
    if decision_level in {DecisionLevel.CALCULATE, DecisionLevel.BID_CANDIDATE} or work_item is None:
        actions.append(
            LotDecisionNextAction(
                action=ActionRecommendation.CALCULATE_MAX_BID,
                label="Рассчитать макс. цену",
                deadline=deadline,
            )
        )
    if (
        decision_level == DecisionLevel.BID_CANDIDATE
        and work_item
        and getattr(work_item, "max_purchase_price", None) is not None
    ):
        actions.append(
            LotDecisionNextAction(
                action=ActionRecommendation.PREPARE_BID,
                label="Готовить заявку",
                deadline=deadline,
            )
        )
    if not actions:
        actions.append(
            LotDecisionNextAction(
                action=ActionRecommendation.MONITOR,
                label="Наблюдать лот",
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
    current_status: str | None,
) -> list[LotDecisionRisk]:
    risks: list[LotDecisionRisk] = []
    if _is_terminal_lot_status(current_status):
        risks.append(
            LotDecisionRisk(
                code="source.terminal_status",
                message=f"Лот недоступен для заявки: {current_status}",
                level="high",
            )
        )
    if work_item and getattr(work_item, "exclude_from_analysis", False):
        risks.append(
            LotDecisionRisk(
                code="manual.excluded",
                message=getattr(work_item, "exclusion_reason", None) or "Lot is manually excluded from analysis",
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
    return (getattr(work_item, "decision_status", None) or "").strip().lower() if work_item else ""


def _manual_final_decision(work_item: AuctionLotWorkItem | None) -> str:
    return (getattr(work_item, "final_decision", None) or "").strip().lower() if work_item else ""


def _recommendation_label(recommendation: ActionRecommendation) -> str:
    return {
        ActionRecommendation.IGNORE: "Игнорировать лот",
        ActionRecommendation.MONITOR: "Наблюдать лот",
        ActionRecommendation.REQUEST_DOCS: "Запросить документы",
        ActionRecommendation.INSPECT: "Осмотреть лот",
        ActionRecommendation.CALCULATE_MAX_BID: "Рассчитать макс. цену",
        ActionRecommendation.PREPARE_BID: "Готовить заявку",
    }[recommendation]


def _decision_level_label(level: DecisionLevel) -> str:
    return {
        DecisionLevel.IGNORE: "Игнорировать",
        DecisionLevel.WATCH: "Наблюдать",
        DecisionLevel.INSPECT: "Осмотреть",
        DecisionLevel.CALCULATE: "Рассчитать",
        DecisionLevel.BID_CANDIDATE: "Кандидат на торги",
    }[level]


def _is_terminal_lot_status(status: str | None) -> bool:
    if not isinstance(status, str):
        return False
    normalized = status.strip().lower()
    if not normalized:
        return False
    return any(
        marker in normalized
        for marker in ("архив", "archived", "заверш", "закончен", "состоял", "состоялись", "подвед", "отмен")
    )


def _resolve_target_roi(
    *,
    profile: LotScoringProfile | None,
    target_roi: Decimal | None,
) -> Decimal:
    if target_roi is not None:
        return target_roi
    if profile is not None and profile.minimum_roi is not None:
        return profile.minimum_roi
    return DEFAULT_TARGET_ROI


def _expected_costs(work_item: AuctionLotWorkItem | None, row: Any) -> tuple[Decimal, bool]:
    values = [
        _first_decimal(
            _work_item_decimal(work_item, field),
            getattr(row, field, None),
        )
        for field in ECONOMICS_COST_FIELDS
    ]
    provided_values = [value for value in values if value is not None]
    return sum(provided_values, Decimal("0")), bool(provided_values)


def _work_item_decimal(work_item: AuctionLotWorkItem | None, field: str) -> Decimal | None:
    if work_item is None:
        return None
    value = getattr(work_item, field, None)
    return value if isinstance(value, Decimal) else None


def _first_decimal(*values: object) -> Decimal | None:
    for value in values:
        if isinstance(value, Decimal):
            return value
    return None


def _economics_missing_inputs(
    *,
    current_price: Decimal | None,
    market_value: Decimal | None,
    has_cost_inputs: bool,
) -> list[str]:
    missing: list[str] = []
    if current_price is None:
        missing.append("current_price")
    if market_value is None:
        missing.append("market_value")
    if not has_cost_inputs:
        missing.append("expected_costs")
    return missing


def _notification_blockers(report: LotDecisionReport) -> list[str]:
    blockers: list[str] = []
    if report.decision_level in {DecisionLevel.IGNORE, DecisionLevel.WATCH}:
        blockers.append("decision_level_not_high")
    if report.recommendation == ActionRecommendation.IGNORE:
        blockers.append("recommendation_ignore")
    for risk in report.risks:
        if risk.level == "high":
            blockers.append(f"high_risk:{risk.code}")
    return blockers


def _cooldown_blocking_statuses() -> tuple[str, str]:
    return (
        TelegramNotificationStatus.PENDING.value,
        TelegramNotificationStatus.SENT.value,
    )


def _notification_reasons(report: LotDecisionReport) -> list[str]:
    reasons: list[str] = []
    high_decision = report.decision_level in {DecisionLevel.CALCULATE, DecisionLevel.BID_CANDIDATE}
    high_score = report.rating_score >= NOTIFICATION_HIGH_SCORE
    profile_fit = _report_has_profile_fit(report)
    near_deadline = _report_is_near_deadline(report)
    changed_opportunity = _report_has_meaningful_opportunity(report)

    if high_decision:
        reasons.append(f"decision_level:{report.decision_level.value}")
    if high_score:
        reasons.append("high_score")
    if profile_fit:
        reasons.append("profile_fit")
    if near_deadline:
        reasons.append("near_deadline")
    if changed_opportunity:
        reasons.append("meaningful_opportunity")

    if not high_decision and not (report.decision_level == DecisionLevel.INSPECT and high_score):
        return []
    if not (high_score or profile_fit or near_deadline):
        return []
    return reasons


def _notification_priority(report: LotDecisionReport, *, blocked: bool) -> str:
    if blocked:
        return "low"
    near_deadline = _report_is_near_deadline(report)
    high_score = report.rating_score >= NOTIFICATION_HIGH_SCORE
    profile_fit = _report_has_profile_fit(report)
    if report.decision_level == DecisionLevel.BID_CANDIDATE and near_deadline:
        return "urgent"
    if report.decision_level == DecisionLevel.BID_CANDIDATE or (high_score and profile_fit):
        return "high"
    if report.decision_level == DecisionLevel.CALCULATE or near_deadline:
        return "medium"
    return "low"


def _report_has_profile_fit(report: LotDecisionReport) -> bool:
    if report.profile_hash is None and report.profile_fit_summary is None:
        return False
    if any(reason.code == "profile.match" for reason in report.reasons):
        return True
    return report.profile_fit_summary is not None and not any(
        risk.code == "profile.blocker" for risk in report.risks
    )


def _report_is_near_deadline(report: LotDecisionReport) -> bool:
    deadline = _parse_report_deadline(report.deadline)
    if deadline is None:
        return False
    generated_at = report.generated_at
    if generated_at.tzinfo is not None:
        generated_at = generated_at.astimezone(UTC).replace(tzinfo=None)
    remaining_hours = (deadline - generated_at).total_seconds() / 3600
    return 0 <= remaining_hours <= NOTIFICATION_NEAR_DEADLINE_HOURS


def _parse_report_deadline(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip()
    for pattern in (
        "%d.%m.%Y %H:%M:%S",
        "%d.%m.%Y %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(normalized[:19], pattern)
        except ValueError:
            continue
    return None


def _report_has_meaningful_opportunity(report: LotDecisionReport) -> bool:
    if report.economics and report.economics.max_buy_price is not None:
        return True
    return bool(report.reasons or report.risks)


def _notification_dedupe_key(report: LotDecisionReport, *, profile_hash: str | None) -> str:
    return "lot-notification:" + _stable_hash(
        {
            "source": report.source,
            "auction_id": report.auction_id,
            "lot_id": report.lot_id,
            "record_id": report.record_id,
            "profile_hash": profile_hash,
            "rating_score": report.rating_score,
            "rating_level": report.rating_level,
            "decision_level": report.decision_level.value,
            "recommendation": report.recommendation.value,
            "economics": report.economics.model_dump(mode="json") if report.economics else None,
            "risk_codes": [risk.code for risk in report.risks],
            "reason_codes": [reason.code for reason in report.reasons],
        }
    )


def _notification_cooldown_key(report: LotDecisionReport, *, profile_hash: str | None) -> str:
    return "lot-notification-cooldown:" + _stable_hash(
        {
            "source": report.source,
            "auction_id": report.auction_id,
            "lot_id": report.lot_id,
            "record_id": report.record_id,
            "profile_hash": profile_hash,
        }
    )


async def _active_telegram_interest_profiles(session: AsyncSession) -> list[UserInterestProfileModel]:
    statement = (
        select(UserInterestProfileModel)
        .where(UserInterestProfileModel.is_active.is_(True))
        .where(UserInterestProfileModel.telegram_enabled.is_(True))
        .order_by(UserInterestProfileModel.owner_user_id.asc(), UserInterestProfileModel.id.asc())
    )
    return list((await session.scalars(statement)).all())


def _user_notification_dedupe_key(
    *,
    user_id: str,
    interest_profile_id: str,
    lot_record_id: int,
    report_hash: str,
) -> str:
    return f"telegram:{user_id}:{interest_profile_id}:{lot_record_id}:{report_hash}"


def _user_notification_cooldown_key(
    *,
    user_id: str,
    interest_profile_id: str,
    lot_record_id: int,
) -> str:
    return f"telegram:{user_id}:{interest_profile_id}:{lot_record_id}"


def _stable_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _field_line(label: str, value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return f"{label}: {_html(text)}"


def _message_items(label: str, values: list[str], limit: int) -> list[str]:
    items = [value.strip() for value in values if isinstance(value, str) and value.strip()]
    if not items:
        return []
    lines = [f"{label}:"]
    lines.extend(f"- {_html(value)}" for value in items[:limit])
    return lines


def _format_decimal(value: Decimal | None) -> str | None:
    if value is None:
        return None
    rounded = value.quantize(Decimal("1")) if value == value.to_integral() else value.normalize()
    return format(rounded, "f")


def _default_lot_link(report: LotDecisionReport) -> str:
    return f"/auctions/lots/{report.record_id}/decision-report"


def _trim_message(text: str, *, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    marker = "\n..."
    return text[: max(0, max_length - len(marker))].rstrip() + marker


def _html(value: object) -> str:
    return escape(str(value), quote=False)
