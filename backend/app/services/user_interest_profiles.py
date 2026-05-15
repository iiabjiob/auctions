from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FilterPresetModel, UserInterestProfileModel, UserModel
from app.schemas.user_interest_profiles import (
    UserInterestProfileCreate,
    UserInterestProfileFromPreset,
    UserInterestProfileResponse,
    UserInterestProfileUpdate,
)
from app.services.auction_catalog import pull_persisted_lots_for_grid
from app.services.lot_decision_report import generate_and_persist_lot_decision_report_snapshot


PROFILE_NOTIFICATION_BACKFILL_LIMIT = 100


class UserInterestProfileService:
    async def list_for_user(self, session: AsyncSession, user: UserModel) -> list[UserInterestProfileResponse]:
        statement = (
            select(UserInterestProfileModel)
            .where(UserInterestProfileModel.owner_user_id == user.id)
            .order_by(UserInterestProfileModel.is_active.desc(), UserInterestProfileModel.name.asc())
        )
        profiles = (await session.scalars(statement)).all()
        return [UserInterestProfileResponse.model_validate(profile, from_attributes=True) for profile in profiles]

    async def create(
        self,
        session: AsyncSession,
        user: UserModel,
        payload: UserInterestProfileCreate,
    ) -> UserInterestProfileResponse:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Profile name is required.")
        await self._ensure_name_available(session, user.id, name)
        profile = UserInterestProfileModel(
            id=f"uip_{uuid4().hex[:24]}",
            owner_user_id=user.id,
            source_filter_preset_id=payload.source_filter_preset_id,
            name=name,
            profile_payload=payload.profile_payload,
            min_rating=payload.min_rating,
            notification_priority_threshold=payload.notification_priority_threshold,
            telegram_enabled=payload.telegram_enabled,
            is_active=payload.is_active,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        session.add(profile)
        await session.flush()
        if profile.source_filter_preset_id:
            preset = await self._get_owned_preset(session, user.id, profile.source_filter_preset_id)
            await _enqueue_existing_notifications_for_preset(session, preset)
        await session.commit()
        await session.refresh(profile)
        return UserInterestProfileResponse.model_validate(profile, from_attributes=True)

    async def create_from_preset(
        self,
        session: AsyncSession,
        user: UserModel,
        payload: UserInterestProfileFromPreset,
    ) -> UserInterestProfileResponse:
        preset = await self._get_owned_preset(session, user.id, payload.preset_id)
        name = (payload.name or preset.name).strip()
        if not name:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Profile name is required.")
        await self._ensure_name_available(session, user.id, name)
        profile_payload = build_profile_payload_from_filter_preset(preset.filters, preset.grid_view)
        min_rating = payload.min_rating
        if min_rating is None:
            min_rating = _filter_int(preset.filters, "minRating", "min_rating")
            if min_rating is None:
                min_rating = _grid_filter_min_number(preset.grid_view, "ratingScore", "rating.score", "rating_score")
            min_rating = min_rating or 0
        profile = UserInterestProfileModel(
            id=f"uip_{uuid4().hex[:24]}",
            owner_user_id=user.id,
            source_filter_preset_id=preset.id,
            name=name,
            profile_payload=profile_payload,
            min_rating=min_rating,
            notification_priority_threshold=payload.notification_priority_threshold,
            telegram_enabled=payload.telegram_enabled,
            is_active=payload.is_active,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        session.add(profile)
        await session.commit()
        await session.refresh(profile)
        return UserInterestProfileResponse.model_validate(profile, from_attributes=True)

    async def update(
        self,
        session: AsyncSession,
        user: UserModel,
        profile_id: str,
        payload: UserInterestProfileUpdate,
    ) -> UserInterestProfileResponse:
        profile = await self._get_owned_profile(session, user.id, profile_id)
        updates = payload.model_dump(exclude_unset=True)

        if "name" in updates:
            next_name = str(updates["name"]).strip()
            if not next_name:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Profile name is required.",
                )
            if next_name != profile.name:
                await self._ensure_name_available(session, user.id, next_name, exclude_id=profile.id)
                profile.name = next_name

        if "profile_payload" in updates:
            profile.profile_payload = updates["profile_payload"]
        if "source_filter_preset_id" in updates:
            profile.source_filter_preset_id = updates["source_filter_preset_id"]
        if "min_rating" in updates:
            profile.min_rating = updates["min_rating"]
        if "notification_priority_threshold" in updates:
            profile.notification_priority_threshold = updates["notification_priority_threshold"]
        if "telegram_enabled" in updates:
            profile.telegram_enabled = bool(updates["telegram_enabled"])
        if "is_active" in updates:
            profile.is_active = bool(updates["is_active"])

        profile.updated_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(profile)
        return UserInterestProfileResponse.model_validate(profile, from_attributes=True)

    async def refresh_from_preset(
        self,
        session: AsyncSession,
        user: UserModel,
        profile_id: str,
    ) -> UserInterestProfileResponse:
        profile = await self._get_owned_profile(session, user.id, profile_id)
        if not profile.source_filter_preset_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Profile is not linked to a preset.")
        preset = await self._get_owned_preset(session, user.id, profile.source_filter_preset_id)
        profile.profile_payload = build_profile_payload_from_filter_preset(preset.filters, preset.grid_view)
        preset_min_rating = _filter_int(preset.filters, "minRating", "min_rating")
        if preset_min_rating is None:
            preset_min_rating = _grid_filter_min_number(preset.grid_view, "ratingScore", "rating.score", "rating_score")
        if preset_min_rating is not None:
            profile.min_rating = preset_min_rating
        profile.updated_at = datetime.now(UTC)
        await session.flush()
        await _enqueue_existing_notifications_for_preset(session, preset)
        await session.commit()
        await session.refresh(profile)
        return UserInterestProfileResponse.model_validate(profile, from_attributes=True)

    async def delete(self, session: AsyncSession, user: UserModel, profile_id: str) -> None:
        profile = await self._get_owned_profile(session, user.id, profile_id)
        await session.delete(profile)
        await session.commit()

    async def _get_owned_profile(
        self,
        session: AsyncSession,
        user_id: str,
        profile_id: str,
    ) -> UserInterestProfileModel:
        statement = select(UserInterestProfileModel).where(
            UserInterestProfileModel.id == profile_id,
            UserInterestProfileModel.owner_user_id == user_id,
        )
        profile = await session.scalar(statement)
        if profile is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found.")
        return profile

    async def _ensure_name_available(
        self,
        session: AsyncSession,
        user_id: str,
        name: str,
        *,
        exclude_id: str | None = None,
    ) -> None:
        statement = select(UserInterestProfileModel).where(
            UserInterestProfileModel.owner_user_id == user_id,
            UserInterestProfileModel.name == name,
        )
        existing = await session.scalar(statement)
        if existing is None:
            return
        if exclude_id and existing.id == exclude_id:
            return
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Profile with this name already exists.")

    async def _get_owned_preset(self, session: AsyncSession, user_id: str, preset_id: str) -> FilterPresetModel:
        statement = select(FilterPresetModel).where(
            FilterPresetModel.id == preset_id,
            FilterPresetModel.owner_user_id == user_id,
        )
        preset = await session.scalar(statement)
        if preset is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Preset not found.")
        return preset


def build_profile_payload_from_filter_preset(filters: dict, grid_view: dict | None = None) -> dict:
    grid_categories = _grid_filter_text_values(
        grid_view,
        "targetCategories",
        "target_categories",
        "categories",
        "analysisCategory",
        "analysis.category",
        "category",
        "modelCategory",
        "model_category",
    )
    grid_budget_min = _grid_filter_min_number(grid_view, "price", "currentPrice", "currentPriceValue", "current_price_value")
    grid_budget_max = _grid_filter_max_number(grid_view, "price", "currentPrice", "currentPriceValue", "current_price_value")
    payload = {
        "profile_identifier": None,
        "target_regions": _filter_text_list(filters, "targetRegions", "target_regions", "regions"),
        "target_categories": _filter_text_list(
            filters,
            "targetCategories",
            "target_categories",
            "categories",
            "analysisCategory",
            "category",
        )
        or grid_categories,
        "budget_min": _filter_number(filters, "minPrice", "min_price", "budget_min") or _format_number(grid_budget_min),
        "budget_max": _filter_number(filters, "maxPrice", "max_price", "budget_max") or _format_number(grid_budget_max),
        "minimum_roi": None,
        "minimum_discount": None,
        "allowed_legal_risks": _filter_text_list(filters, "allowedLegalRisks", "allowed_legal_risks")
        or ["low", "medium"],
        "max_distance_km": None,
        "stop_words": _filter_text_list(filters, "stopWords", "stop_words"),
        "desired_keywords": _filter_text_list(filters, "desiredKeywords", "desired_keywords", "q", "status"),
        "strategy": "balanced",
        "weights": {},
    }
    return {key: value for key, value in payload.items() if value not in (None, [], {})}


def _filter_text_list(filters: dict, *keys: str) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for key in keys:
        value = filters.get(key)
        candidates = value if isinstance(value, list) else str(value or "").split(",")
        for candidate in candidates:
            text = str(candidate or "").strip()
            normalized = text.casefold()
            if not text or normalized in seen or normalized == "all":
                continue
            seen.add(normalized)
            values.append(text)
    return values


def _filter_number(filters: dict, *keys: str) -> str | None:
    for key in keys:
        value = filters.get(key)
        if value is None:
            continue
        normalized = str(value).strip().replace(" ", "").replace(",", ".")
        if not normalized:
            continue
        try:
            number = float(normalized)
        except ValueError:
            continue
        if number.is_integer():
            return str(int(number))
        return str(number)
    return None


def _filter_int(filters: dict, *keys: str) -> int | None:
    value = _filter_number(filters, *keys)
    if value is None:
        return None
    return max(0, min(100, int(float(value))))


def _grid_filter_model(grid_view: dict | None) -> dict:
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


def _grid_filter_text_values(grid_view: dict | None, *keys: str) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for payload in _grid_filter_payloads(grid_view, *keys):
        for value in _text_values_from_filter_payload(payload):
            normalized = value.casefold()
            if normalized not in seen:
                seen.add(normalized)
                values.append(value)
    return values


def _grid_filter_min_number(grid_view: dict | None, *keys: str) -> int | None:
    values: list[Decimal] = []
    for payload in _grid_filter_payloads(grid_view, *keys):
        values.extend(_number_bounds_from_filter_payload(payload)[0])
    return _decimal_to_int(max(values)) if values else None


def _grid_filter_max_number(grid_view: dict | None, *keys: str) -> int | None:
    values: list[Decimal] = []
    for payload in _grid_filter_payloads(grid_view, *keys):
        values.extend(_number_bounds_from_filter_payload(payload)[1])
    return _decimal_to_int(min(values)) if values else None


def _grid_filter_payloads(grid_view: dict | None, *keys: str) -> list[dict]:
    filter_model = _grid_filter_model(grid_view)
    payloads: list[dict] = []
    key_set = set(keys)
    for section_name in ("columnFilters", "advancedFilters"):
        section = filter_model.get(section_name)
        if not isinstance(section, dict):
            continue
        for key in key_set:
            payload = section.get(key)
            if isinstance(payload, dict):
                payloads.append(payload)

    advanced_expression = filter_model.get("advancedExpression")
    payloads.extend(_advanced_expression_payloads(advanced_expression, key_set))
    return payloads


def _advanced_expression_payloads(payload: object, keys: set[str]) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    kind = payload.get("kind")
    if kind == "condition" and payload.get("key") in keys:
        return [payload]
    if kind == "group":
        result: list[dict] = []
        for child in payload.get("children") or []:
            result.extend(_advanced_expression_payloads(child, keys))
        return result
    if kind == "not":
        return _advanced_expression_payloads(payload.get("child"), keys)
    return []


def _text_values_from_filter_payload(payload: dict) -> list[str]:
    if payload.get("kind") == "valueSet":
        tokens = payload.get("tokens")
        return [_text_value_from_token(token) for token in tokens if isinstance(token, str)] if isinstance(tokens, list) else []
    if payload.get("kind") == "predicate" or payload.get("kind") == "condition":
        value = payload.get("value")
        return [str(value).strip()] if value is not None and str(value).strip() else []

    values: list[str] = []
    for clause in payload.get("clauses") or []:
        if not isinstance(clause, dict):
            continue
        value = clause.get("value")
        if value is not None and str(value).strip():
            values.append(str(value).strip())
    return values


def _number_bounds_from_filter_payload(payload: dict) -> tuple[list[Decimal], list[Decimal]]:
    min_values: list[Decimal] = []
    max_values: list[Decimal] = []
    clauses = payload.get("clauses") if isinstance(payload.get("clauses"), list) else [payload]
    for clause in clauses:
        if not isinstance(clause, dict):
            continue
        operator = str(clause.get("operator") or "").strip()
        value = _decimal_from_filter_value(clause.get("value"))
        value2 = _decimal_from_filter_value(clause.get("value2"))
        if value is None:
            continue
        if operator in {"gte", "gt"}:
            min_values.append(value)
        elif operator in {"lte", "lt"}:
            max_values.append(value)
        elif operator == "between":
            min_values.append(value)
            if value2 is not None:
                max_values.append(value2)
        elif operator == "equals":
            min_values.append(value)
            max_values.append(value)
    return min_values, max_values


def _text_value_from_token(token: str) -> str:
    if token.startswith("string:"):
        return token.removeprefix("string:").strip()
    return token.strip()


def _decimal_from_filter_value(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value).strip().replace(" ", "").replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def _decimal_to_int(value: Decimal) -> int:
    return max(0, int(value))


def _format_number(value: int | None) -> str | None:
    return str(value) if value is not None else None


async def _enqueue_existing_notifications_for_preset(
    session: AsyncSession,
    preset: FilterPresetModel,
    *,
    limit: int = PROFILE_NOTIFICATION_BACKFILL_LIMIT,
) -> None:
    rows, _ = await pull_persisted_lots_for_grid(
        session,
        start_row=0,
        end_row=limit,
        period=str(preset.filters.get("period") or "month"),
        source=str(preset.filters.get("source") or "all"),
        status=_optional_text(preset.filters.get("status")),
        analysis_color=_optional_text(preset.filters.get("analysisColor") or preset.filters.get("analysis_color")),
        min_price=_optional_decimal(preset.filters.get("minPrice") or preset.filters.get("min_price")),
        max_price=_optional_decimal(preset.filters.get("maxPrice") or preset.filters.get("max_price")),
        only_new=bool(preset.filters.get("onlyNew") or preset.filters.get("only_new")),
        shortlist=bool(preset.filters.get("shortlist")),
        min_rating=_filter_int(preset.filters, "minRating", "min_rating"),
        include_archived=False,
        sort_model=[{"key": "ratingScore", "direction": "desc"}],
        grid_filter=_grid_filter_model(preset.grid_view) or None,
    )
    for record, _row in rows:
        await generate_and_persist_lot_decision_report_snapshot(session, record)


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _optional_decimal(value: object) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return Decimal(str(value).strip().replace(" ", "").replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


user_interest_profile_service = UserInterestProfileService()
