from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FilterPresetModel, UserInterestProfileModel
from app.models.auction import AuctionLotDetailCache, AuctionLotRecord, AuctionLotWorkItem
from app.schemas.auctions import LotDatagridFilters
from app.schemas.lot_decision_report import LotDecisionReport
from app.schemas.scoring_profile_fit import LotProfileFitEvaluation
from app.services.auction_catalog import _build_persisted_lots_statement
from app.services.auction_sources import SOURCE_PROVIDERS


@dataclass(frozen=True)
class UserInterestMatchResult:
    matches: bool
    reasons: tuple[str, ...]
    blockers: tuple[str, ...]
    profile_hash: str
    profile_fit: LotProfileFitEvaluation


async def evaluate_user_interest_match(
    record: AuctionLotRecord,
    interest_profile: UserInterestProfileModel,
    *,
    session: AsyncSession | None = None,
    detail_cache: AuctionLotDetailCache | None = None,
    work_item: AuctionLotWorkItem | None = None,
    report: LotDecisionReport | None = None,
    require_telegram_enabled: bool = True,
) -> UserInterestMatchResult:
    del work_item

    if session is not None and getattr(interest_profile, "source_filter_preset_id", None):
        try:
            preset = await _get_owned_preset(session, interest_profile.owner_user_id, interest_profile.source_filter_preset_id)
        except ValueError:
            preset = None
        if preset is not None:
            return await evaluate_saved_slice_match(
                session,
                record,
                interest_profile,
                preset,
                report=report,
                require_telegram_enabled=require_telegram_enabled,
            )

    return UserInterestMatchResult(
        matches=False,
        reasons=(),
        blockers=("Профиль не привязан к сохраненному срезу",),
        profile_hash="",
        profile_fit=LotProfileFitEvaluation(
            profile_identifier=getattr(interest_profile, "id", None),
            matches_profile=False,
            reasons=[],
            blockers=["Профиль не привязан к сохраненному срезу"],
        ),
    )


async def evaluate_saved_slice_match(
    session: AsyncSession,
    record: AuctionLotRecord,
    interest_profile: UserInterestProfileModel,
    preset: FilterPresetModel,
    *,
    report: LotDecisionReport | None = None,
    require_telegram_enabled: bool = True,
) -> UserInterestMatchResult:
    slice_hash = build_saved_slice_hash(preset)
    matches_slice = await _record_matches_saved_slice(session, record, preset)
    rating_score = int(report.rating_score if report is not None else getattr(record, "rating_score", 0) or 0)
    min_rating = int(getattr(interest_profile, "min_rating", 0) or 0)

    reasons: list[str] = []
    blockers: list[str] = []

    if not getattr(interest_profile, "is_active", False):
        blockers.append("Профиль интересов отключен")
    if require_telegram_enabled and not getattr(interest_profile, "telegram_enabled", False):
        blockers.append("Telegram-уведомления отключены для профиля")
    if rating_score < min_rating:
        blockers.append(f"Рейтинг ниже порога профиля: {rating_score} < {min_rating}")
    if not matches_slice:
        blockers.append("Лот не попадает в сохраненный срез")
    else:
        reasons.append(f"Лот попадает в сохраненный срез: {preset.name}")

    if not blockers and not reasons:
        reasons.append("Лот соответствует сохраненному срезу")

    profile_fit = LotProfileFitEvaluation(
        profile_identifier=preset.id,
        matches_profile=not blockers,
        dimensions={},
        reasons=list(reasons),
        blockers=list(blockers),
    )
    return UserInterestMatchResult(
        matches=not blockers,
        reasons=tuple(reasons),
        blockers=tuple(blockers),
        profile_hash=slice_hash,
        profile_fit=profile_fit,
    )


def build_saved_slice_hash(preset: FilterPresetModel) -> str:
    payload = {
        "scope": getattr(preset, "scope", None),
        "filters": _normalize_saved_slice_filters(preset.filters),
        "grid_filter": _normalize_saved_slice_grid_filter(preset.grid_view),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def build_saved_slice_match_statement(record_id: int, preset: FilterPresetModel):
    filters = _saved_slice_filters_to_datagrid_filters(preset.filters)
    grid_filter = _normalize_saved_slice_grid_filter(preset.grid_view)
    statement = _build_persisted_lots_statement(filters, tuple(SOURCE_PROVIDERS), grid_filter=grid_filter)
    return statement.where(AuctionLotRecord.id == record_id).with_only_columns(AuctionLotRecord.id).limit(1)


async def _record_matches_saved_slice(
    session: AsyncSession,
    record: AuctionLotRecord,
    preset: FilterPresetModel,
) -> bool:
    statement = build_saved_slice_match_statement(int(record.id), preset)
    return await session.scalar(statement) is not None


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


def _saved_slice_filters_to_datagrid_filters(filters: dict) -> LotDatagridFilters:
    return LotDatagridFilters(
        period=str(filters.get("period") or "month"),
        source=_text_filter_value(filters, "source"),
        status=_text_filter_value(filters, "status"),
        analysis_color=_text_filter_value(filters, "analysisColor", "analysis_color"),
        min_price=_decimal_filter_value(filters, "minPrice", "min_price"),
        max_price=_decimal_filter_value(filters, "maxPrice", "max_price"),
        only_new=bool(filters.get("onlyNew") or filters.get("only_new")),
        shortlist=bool(filters.get("shortlist")),
        min_rating=_int_filter_value(filters, "minRating", "min_rating"),
        include_archived=bool(filters.get("includeArchived") or filters.get("include_archived")),
    )


def _normalize_saved_slice_filters(filters: dict | None) -> dict[str, object]:
    if not isinstance(filters, dict):
        return {}
    normalized: dict[str, object] = {}
    for key, value in filters.items():
        if key == "period":
            normalized[key] = str(value).strip() if isinstance(value, str) and value.strip() else "month"
        elif key in {"source", "status", "analysisColor", "analysis_color"}:
            text = str(value).strip() if value is not None else ""
            if text:
                normalized[key] = text
        elif key in {"minPrice", "maxPrice", "min_price"}:
            number = _decimal_filter_value({key: value}, key)
            if number is not None:
                normalized[key] = str(number)
        elif key in {"minRating", "min_rating"}:
            number = _int_filter_value({key: value}, key)
            if number is not None:
                normalized[key] = number
        elif key in {"onlyNew", "shortlist", "includeArchived", "only_new", "include_archived"}:
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


def _text_filter_value(filters: dict, *keys: str) -> str | None:
    for key in keys:
        value = filters.get(key)
        if isinstance(value, str):
            text = value.strip()
            if text:
                return text
    return None


def _decimal_filter_value(filters: dict, *keys: str):
    for key in keys:
        value = filters.get(key)
        if value in (None, ""):
            continue
        try:
            return Decimal(str(value).replace(" ", "").replace(",", "."))
        except (TypeError, ValueError):
            continue
    return None


def _int_filter_value(filters: dict, *keys: str) -> int | None:
    for key in keys:
        value = filters.get(key)
        if value in (None, ""):
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None
