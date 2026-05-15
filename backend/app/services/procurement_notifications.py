from __future__ import annotations

import hashlib
import html
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FilterPresetModel, UserInterestProfileModel, UserTelegramBindingModel
from app.models.procurement import ProcurementLotRecord, ProcurementTelegramNotificationOutbox
from app.schemas.lot_decision_report import TelegramNotificationStatus
from app.schemas.procurement_grid import ProcurementLotsGridQueryOptions
from app.services.procurement_grid import _build_procurement_lots_statement, _merge_query_options_into_filter_model


BLOCKING_STATUSES = (TelegramNotificationStatus.PENDING.value, TelegramNotificationStatus.SENT.value)
DEFAULT_COOLDOWN_SECONDS = 6 * 60 * 60


async def enqueue_procurement_telegram_notifications(
    session: AsyncSession,
    record: ProcurementLotRecord,
    *,
    now: datetime | None = None,
    cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS,
) -> list[ProcurementTelegramNotificationOutbox]:
    del cooldown_seconds

    if record.id is None:
        return []

    current_time = now or datetime.now(UTC)
    profiles = await _active_telegram_interest_profiles(session)
    telegram_bindings = await _telegram_bindings_by_user_id(session, {profile.owner_user_id for profile in profiles})
    entries: list[ProcurementTelegramNotificationOutbox] = []
    seen_user_lot_keys: set[tuple[str, int]] = set()

    for interest_profile in profiles:
        user_lot_key = (interest_profile.owner_user_id, int(record.id))
        if user_lot_key in seen_user_lot_keys:
            continue
        preset = await _get_owned_preset(session, interest_profile.owner_user_id, interest_profile.source_filter_preset_id)
        if preset.scope != "procurement":
            continue
        if not await _record_matches_saved_slice(session, record, preset):
            continue

        binding = telegram_bindings.get(interest_profile.owner_user_id)
        if binding is None or not binding.telegram_chat_id:
            continue

        seen_user_lot_keys.add(user_lot_key)
        event_type = _delivery_event_type(interest_profile.owner_user_id)
        existing_user_lot_delivery = await _existing_user_lot_delivery(
            session,
            user_id=interest_profile.owner_user_id,
            record_id=int(record.id),
            event_type=event_type,
        )
        if existing_user_lot_delivery is not None:
            entries.append(existing_user_lot_delivery)
            continue

        slice_hash = build_saved_slice_hash(preset)
        dedupe_key = _dedupe_key(
            user_id=interest_profile.owner_user_id,
            profile_id=interest_profile.id,
            record_id=int(record.id),
            slice_hash=slice_hash,
        )
        existing = await session.scalar(
            select(ProcurementTelegramNotificationOutbox).where(
                ProcurementTelegramNotificationOutbox.dedupe_key == dedupe_key,
            )
        )
        if existing is not None:
            entries.append(existing)
            continue

        cooldown_key = _cooldown_key(
            user_id=interest_profile.owner_user_id,
            record_id=int(record.id),
        )
        entry = ProcurementTelegramNotificationOutbox(
            procurement_lot_record_id=int(record.id),
            event_type=event_type,
            user_id=interest_profile.owner_user_id,
            telegram_chat_id=binding.telegram_chat_id,
            dedupe_key=dedupe_key,
            cooldown_key=cooldown_key,
            status=TelegramNotificationStatus.PENDING.value,
            priority=_priority_for_record(record),
            message_payload=_message_payload(record, preset),
            event_hash=_stable_hash(
                {
                    "record_id": record.id,
                    "slice_hash": slice_hash,
                    "record_hash": record.content_hash,
                    "preset_id": preset.id,
                }
            ),
            scheduled_at=current_time,
        )
        session.add(entry)
        entries.append(entry)

    if entries:
        await session.flush()
    return entries


async def _active_telegram_interest_profiles(session: AsyncSession) -> list[UserInterestProfileModel]:
    statement = (
        select(UserInterestProfileModel)
        .where(UserInterestProfileModel.is_active.is_(True))
        .where(UserInterestProfileModel.telegram_enabled.is_(True))
        .where(UserInterestProfileModel.source_filter_preset_id.is_not(None))
        .order_by(UserInterestProfileModel.owner_user_id.asc(), UserInterestProfileModel.id.asc())
    )
    return list((await session.scalars(statement)).all())


async def _record_matches_saved_slice(
    session: AsyncSession,
    record: ProcurementLotRecord,
    preset: FilterPresetModel,
) -> bool:
    statement = build_saved_slice_match_statement(int(record.id), preset)
    return await session.scalar(statement) is not None


def build_saved_slice_hash(preset: FilterPresetModel) -> str:
    payload = {
        "scope": getattr(preset, "scope", None),
        "filters": _normalize_saved_slice_filters(preset.filters),
        "grid_filter": _normalize_saved_slice_grid_filter(preset.grid_view),
    }
    return _stable_hash(payload)


def build_saved_slice_match_statement(record_id: int, preset: FilterPresetModel):
    query = _saved_slice_query_options(preset.filters, preset.grid_view)
    grid_filter = _merge_query_options_into_filter_model(query.filter_model, query)
    statement = _build_procurement_lots_statement(grid_filter=grid_filter)
    return statement.where(ProcurementLotRecord.id == record_id).with_only_columns(ProcurementLotRecord.id).limit(1)


async def _get_owned_preset(
    session: AsyncSession,
    owner_user_id: str,
    preset_id: str,
) -> FilterPresetModel:
    statement = select(FilterPresetModel).where(
        FilterPresetModel.id == preset_id,
        FilterPresetModel.owner_user_id == owner_user_id,
    )
    preset = await session.scalar(statement)
    if preset is None:
        raise ValueError("Preset not found")
    return preset


async def _telegram_bindings_by_user_id(
    session: AsyncSession,
    user_ids: set[str],
) -> dict[str, UserTelegramBindingModel]:
    if not user_ids:
        return {}
    statement = select(UserTelegramBindingModel).where(UserTelegramBindingModel.user_id.in_(sorted(user_ids)))
    bindings = (await session.scalars(statement)).all()
    return {binding.user_id: binding for binding in bindings}


async def _existing_user_lot_delivery(
    session: AsyncSession,
    *,
    user_id: str,
    record_id: int,
    event_type: str,
) -> ProcurementTelegramNotificationOutbox | None:
    return await session.scalar(
        select(ProcurementTelegramNotificationOutbox)
        .where(ProcurementTelegramNotificationOutbox.user_id == user_id)
        .where(ProcurementTelegramNotificationOutbox.procurement_lot_record_id == record_id)
        .where(ProcurementTelegramNotificationOutbox.event_type == event_type)
        .where(ProcurementTelegramNotificationOutbox.status.in_(BLOCKING_STATUSES))
        .order_by(
            ProcurementTelegramNotificationOutbox.sent_at.desc().nullslast(),
            ProcurementTelegramNotificationOutbox.scheduled_at.desc(),
            ProcurementTelegramNotificationOutbox.id.desc(),
        )
        .limit(1)
    )


def _saved_slice_query_options(filters: dict, grid_view: dict | None = None) -> ProcurementLotsGridQueryOptions:
    return ProcurementLotsGridQueryOptions(
        source=_text_filter(filters, "source", default=None),
        law=_text_filter(filters, "law", default=None),
        status=_text_filter(filters, "status", default=None),
        workflow_status=_text_filter(filters, "workflowStatus", "workflow_status", default=None),
        assignee=_text_filter(filters, "assignee", default=None),
        category=_text_filter(filters, "category", default=None),
        min_price=_decimal_filter(filters, "minPrice", "min_price"),
        max_price=_decimal_filter(filters, "maxPrice", "max_price"),
        min_score=_int_filter(filters, "minScore", "min_score"),
        only_new=bool(filters.get("onlyNew") or filters.get("only_new")),
        filter_model=_normalize_saved_slice_grid_filter(grid_view) or None,
    )


def _normalize_saved_slice_filters(filters: dict | None) -> dict[str, object]:
    if not isinstance(filters, dict):
        return {}
    normalized: dict[str, object] = {}
    for key, value in filters.items():
        if key == "source":
            text = _text_filter({key: value}, key, default=None)
            if text is not None:
                normalized[key] = text
        elif key in {"law", "status", "workflowStatus", "workflow_status", "assignee", "category"}:
            text = str(value).strip() if value is not None else ""
            if text:
                normalized[key] = text
        elif key in {"minPrice", "maxPrice", "min_price"}:
            number = _decimal_filter({key: value}, key)
            if number is not None:
                normalized[key] = str(number)
        elif key in {"minScore", "min_score"}:
            number = _int_filter({key: value}, key)
            if number is not None:
                normalized[key] = number
        elif key in {"onlyNew", "only_new"}:
            normalized[key] = bool(value)
        else:
            normalized[key] = value
    return dict(sorted(normalized.items(), key=lambda item: item[0]))


def _normalize_saved_slice_grid_filter(grid_view: dict | None) -> dict[str, object]:
    if not isinstance(grid_view, dict):
        return {}
    state = grid_view.get("state")
    if not isinstance(state, dict):
        return {}
    rows = state.get("rows")
    if not isinstance(rows, dict):
        return {}
    snapshot = rows.get("snapshot")
    if not isinstance(snapshot, dict):
        return {}
    filter_model = snapshot.get("filterModel")
    return filter_model if isinstance(filter_model, dict) else {}


def _priority_for_record(record: ProcurementLotRecord) -> str:
    status = (record.workflow_status or "").strip().lower()
    if status == "decision":
        return "urgent"
    if int(record.attractiveness_score or 0) >= 75:
        return "high"
    if int(record.attractiveness_score or 0) >= 50:
        return "medium"
    return "low"


def _message_payload(record: ProcurementLotRecord, preset: FilterPresetModel) -> dict[str, str]:
    lines = [
        "<b>Тендер попал в сохраненный срез</b>",
        f"Срез: {html.escape(preset.name)}",
        f"Рейтинг: {int(record.attractiveness_score or 0)} ({html.escape(record.attractiveness_level or '-')})",
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
    return {"text": "\n".join(lines), "parse_mode": "HTML"}


def _delivery_event_type(user_id: str) -> str:
    return f"saved_slice:{user_id}"


def _dedupe_key(*, user_id: str, profile_id: str, record_id: int, slice_hash: str) -> str:
    return f"procurement-telegram:{user_id}:{profile_id}:{record_id}:{slice_hash}"


def _cooldown_key(*, user_id: str, record_id: int) -> str:
    return f"procurement-telegram:{user_id}:{record_id}"


def _text_filter(filters: dict, *keys: str, default: str | None = "") -> str | None:
    for key in keys:
        value = filters.get(key)
        if isinstance(value, str):
            text = value.strip()
            if not text:
                continue
            if text.lower() == "all":
                return None
            return text
    return default


def _decimal_filter(filters: dict, *keys: str):
    for key in keys:
        value = filters.get(key)
        if value in (None, ""):
            continue
        try:
            return Decimal(str(value).replace(" ", "").replace(",", "."))
        except (TypeError, ValueError):
            continue
    return None


def _int_filter(filters: dict, *keys: str) -> int | None:
    for key in keys:
        value = filters.get(key)
        if value in (None, ""):
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _money(value: Decimal) -> str:
    return f"{value:,.0f} ₽".replace(",", " ")


def _percent(value: Decimal) -> str:
    return f"{(value * Decimal('100')):.1f}%"


def _stable_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()
