from __future__ import annotations

import hashlib
import html
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.procurement import ProcurementLotRecord, ProcurementTelegramNotificationOutbox
from app.schemas.lot_decision_report import TelegramNotificationStatus


PRIORITY_SCORE_THRESHOLD = 75
PROFIT_THRESHOLD = Decimal("500000")
PROFITABILITY_THRESHOLD = Decimal("0.20")
DEADLINE_HOURS_THRESHOLD = 48
READY_WORKFLOW_STATUSES = {"decision"}
BLOCKING_STATUSES = (TelegramNotificationStatus.PENDING.value, TelegramNotificationStatus.SENT.value)


@dataclass(frozen=True, slots=True)
class ProcurementNotificationEvent:
    event_type: str
    priority: str
    reasons: list[str]
    event_hash: str


async def enqueue_procurement_telegram_notifications(
    session: AsyncSession,
    record: ProcurementLotRecord,
    *,
    now: datetime | None = None,
) -> list[ProcurementTelegramNotificationOutbox]:
    current_time = now or datetime.now(UTC)
    entries: list[ProcurementTelegramNotificationOutbox] = []
    for event in evaluate_procurement_notification_events(record, now=current_time):
        existing = await _existing_delivery(session, record=record, event_type=event.event_type)
        if existing is not None:
            continue
        entry = ProcurementTelegramNotificationOutbox(
            procurement_lot_record_id=int(record.id),
            event_type=event.event_type,
            dedupe_key=_dedupe_key(record, event),
            cooldown_key=_cooldown_key(record, event),
            status=TelegramNotificationStatus.PENDING.value,
            priority=event.priority,
            message_payload=_message_payload(record, event),
            event_hash=event.event_hash,
            scheduled_at=current_time,
        )
        session.add(entry)
        entries.append(entry)
    if entries:
        await session.flush()
    return entries


def evaluate_procurement_notification_events(
    record: ProcurementLotRecord,
    *,
    now: datetime | None = None,
) -> list[ProcurementNotificationEvent]:
    current_time = now or datetime.now(UTC)
    events: list[ProcurementNotificationEvent] = []

    if int(record.attractiveness_score or 0) > PRIORITY_SCORE_THRESHOLD:
        events.append(
            _event(
                "priority_tender",
                "high",
                record,
                ["score_above_75", f"score:{record.attractiveness_score}"],
            )
        )
    if record.net_profit is not None and record.net_profit > PROFIT_THRESHOLD:
        events.append(
            _event(
                "net_profit_gt_500k",
                "high",
                record,
                ["net_profit_gt_500k", f"net_profit:{record.net_profit}"],
            )
        )
    if record.profitability is not None and record.profitability > PROFITABILITY_THRESHOLD:
        events.append(
            _event(
                "profitability_gt_20",
                "high",
                record,
                ["profitability_gt_20", f"profitability:{record.profitability}"],
            )
        )
    hours_to_deadline = _hours_to_deadline(record, current_time)
    if hours_to_deadline is not None and 0 <= hours_to_deadline <= DEADLINE_HOURS_THRESHOLD:
        events.append(
            _event(
                "deadline_under_48h",
                "urgent",
                record,
                ["deadline_under_48h", f"hours_to_deadline:{hours_to_deadline}"],
            )
        )
    if (record.workflow_status or "").strip().lower() in READY_WORKFLOW_STATUSES:
        events.append(
            _event(
                "owner_decision_ready",
                "urgent",
                record,
                ["owner_decision_ready", f"workflow_status:{record.workflow_status}"],
            )
        )
    return events


async def _existing_delivery(
    session: AsyncSession,
    *,
    record: ProcurementLotRecord,
    event_type: str,
) -> ProcurementTelegramNotificationOutbox | None:
    return await session.scalar(
        select(ProcurementTelegramNotificationOutbox)
        .where(ProcurementTelegramNotificationOutbox.procurement_lot_record_id == record.id)
        .where(ProcurementTelegramNotificationOutbox.event_type == event_type)
        .where(ProcurementTelegramNotificationOutbox.status.in_(BLOCKING_STATUSES))
        .order_by(
            ProcurementTelegramNotificationOutbox.sent_at.desc().nullslast(),
            ProcurementTelegramNotificationOutbox.scheduled_at.desc(),
            ProcurementTelegramNotificationOutbox.id.desc(),
        )
        .limit(1)
    )


def _event(
    event_type: str,
    priority: str,
    record: ProcurementLotRecord,
    reasons: list[str],
) -> ProcurementNotificationEvent:
    payload = {
        "event_type": event_type,
        "record_id": record.id,
        "source": record.source_code,
        "external_id": record.external_id,
        "registry_number": record.registry_number,
        "score": record.attractiveness_score,
        "net_profit": str(record.net_profit) if record.net_profit is not None else None,
        "profitability": str(record.profitability) if record.profitability is not None else None,
        "workflow_status": record.workflow_status,
        "deadline": record.application_deadline_at.isoformat() if record.application_deadline_at else None,
        "reasons": reasons,
    }
    return ProcurementNotificationEvent(
        event_type=event_type,
        priority=priority,
        reasons=reasons,
        event_hash=_stable_hash(payload),
    )


def _message_payload(record: ProcurementLotRecord, event: ProcurementNotificationEvent) -> dict[str, str]:
    lines = [
        "<b>Тендер требует внимания</b>",
        f"Событие: {html.escape(_event_label(event.event_type))}",
        f"Балл: {int(record.attractiveness_score or 0)} ({html.escape(record.attractiveness_level or '-')})",
        f"Номер: {html.escape(record.registry_number)}",
        f"Предмет: {html.escape((record.title or 'Без названия')[:240])}",
    ]
    if record.customer_name:
        lines.append(f"Заказчик: {html.escape(record.customer_name[:160])}")
    if record.initial_price_value is not None:
        lines.append(f"НМЦК: {_money(record.initial_price_value)}")
    if record.net_profit is not None:
        lines.append(f"Чистая прибыль: {_money(record.net_profit)}")
    if record.profitability is not None:
        lines.append(f"Маржинальность: {_percent(record.profitability)}")
    if record.application_deadline_at is not None:
        lines.append(f"Заявки до: {html.escape(record.application_deadline_at.isoformat())}")
    if record.notice_url:
        lines.append(f'<a href="{html.escape(record.notice_url, quote=True)}">Открыть закупку</a>')
    if event.reasons:
        lines.append("Причины: " + html.escape(", ".join(event.reasons[:4])))
    return {"text": "\n".join(lines), "parse_mode": "HTML"}


def _dedupe_key(record: ProcurementLotRecord, event: ProcurementNotificationEvent) -> str:
    return f"procurement-telegram:{record.id}:{event.event_type}:{event.event_hash}"


def _cooldown_key(record: ProcurementLotRecord, event: ProcurementNotificationEvent) -> str:
    return f"procurement-telegram:{record.id}:{event.event_type}"


def _hours_to_deadline(record: ProcurementLotRecord, now: datetime) -> int | None:
    if record.application_deadline_at is None:
        return None
    delta = record.application_deadline_at - now
    return int(delta.total_seconds() // 3600)


def _event_label(event_type: str) -> str:
    return {
        "priority_tender": "новый приоритетный тендер",
        "net_profit_gt_500k": "чистая прибыль выше 500k",
        "profitability_gt_20": "маржинальность выше 20%",
        "deadline_under_48h": "дедлайн меньше 48 часов",
        "owner_decision_ready": "тендер готов к решению владельца",
    }.get(event_type, event_type)


def _money(value: Decimal) -> str:
    return f"{value:,.0f} ₽".replace(",", " ")


def _percent(value: Decimal) -> str:
    return f"{(value * Decimal('100')):.1f}%"


def _stable_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()
