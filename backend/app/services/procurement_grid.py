from __future__ import annotations

from datetime import datetime
from decimal import Decimal, DecimalException
from typing import Any

from sqlalchemy import String, and_, cast, func, not_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.grid import GridRevisionModel
from app.models.procurement import ProcurementLotRecord
from app.schemas.auctions import LotDatagridHistogramEntry
from app.schemas.procurement_grid import (
    ProcurementLotsGridHistogramRequest,
    ProcurementLotsGridHistogramResponse,
    ProcurementLotsGridPullRequest,
    ProcurementLotsGridPullResponse,
    ProcurementLotsGridPullRow,
    ProcurementLotsGridQueryOptions,
    ProcurementLotsGridSummary,
)
from app.services.procurement_grid_state import (
    DEFAULT_GRID_WORKSPACE_ID,
    PROCUREMENT_LOTS_TABLE_ID,
    procurement_lot_grid_row_id,
)


DEFAULT_QUICK_FILTER_COLUMNS = (
    "registryNumber",
    "title",
    "customerName",
    "customerInn",
    "category",
    "status",
    "workflowStatus",
    "assignee",
)
GRID_COLUMN_ALIASES = {
    "application_deadline_at": "applicationDeadline",
    "applicationDeadlineAt": "applicationDeadline",
    "attractiveness.score": "score",
    "attractiveness.level": "scoreLevel",
    "customer_inn": "customerInn",
    "customer_name": "customerName",
    "delivery_region": "deliveryRegion",
    "external_id": "externalId",
    "filter_reason": "filterReason",
    "initial_price_value": "initialPrice",
    "is_new": "isNew",
    "net_profit": "netProfit",
    "publication_at": "publicationDate",
    "registry_number": "registryNumber",
    "workflow_status": "workflowStatus",
}


async def read_procurement_grid_dataset_version(
    session: AsyncSession,
    *,
    workspace_id: str = DEFAULT_GRID_WORKSPACE_ID,
    table_id: str = PROCUREMENT_LOTS_TABLE_ID,
) -> int:
    version = await session.scalar(
        select(GridRevisionModel.dataset_version).where(
            GridRevisionModel.workspace_id == workspace_id,
            GridRevisionModel.table_id == table_id,
        )
    )
    return int(version or 0)


async def pull_procurement_lots_grid(
    session: AsyncSession,
    request: ProcurementLotsGridPullRequest,
    *,
    workspace_id: str = DEFAULT_GRID_WORKSPACE_ID,
) -> ProcurementLotsGridPullResponse:
    dataset_version = await read_procurement_grid_dataset_version(session, workspace_id=workspace_id)
    grid_filter = _merge_query_options_into_filter_model(request.filter_model, request)
    rows, total = await pull_procurement_lots_for_grid(
        session,
        start_row=request.resolved_start_row,
        end_row=request.resolved_end_row,
        sort_model=_normalize_sort_model(request.sort_model),
        grid_filter=grid_filter,
    )
    summary = await summarize_procurement_lots_for_grid(session, grid_filter=grid_filter)
    return ProcurementLotsGridPullResponse(
        rows=[
            ProcurementLotsGridPullRow(
                id=procurement_lot_grid_row_id(record),
                index=request.resolved_start_row + offset,
                row=row,
            )
            for offset, (record, row) in enumerate(rows)
        ],
        total=total,
        dataset_version=dataset_version,
        summary=summary,
    )


async def get_procurement_lots_grid_histogram(
    session: AsyncSession,
    request: ProcurementLotsGridHistogramRequest,
) -> ProcurementLotsGridHistogramResponse:
    grid_filter = _merge_query_options_into_filter_model(
        _histogram_filter_model(request.filter_model, request.column_id, request.options),
        request,
    )
    if _grid_filter_has_quick_filter(grid_filter):
        return ProcurementLotsGridHistogramResponse(column_id=request.column_id, entries=[])
    entries = await list_procurement_lot_column_histogram(
        session,
        column_id=request.column_id,
        histogram_options=request.options,
        sort_model=_normalize_sort_model(request.sort_model),
        grid_filter=grid_filter,
    )
    return ProcurementLotsGridHistogramResponse(column_id=request.column_id, entries=entries)


async def pull_procurement_lots_for_grid(
    session: AsyncSession,
    *,
    start_row: int,
    end_row: int,
    sort_model: list[dict[str, str]] | None = None,
    grid_filter: dict[str, Any] | None = None,
) -> tuple[list[tuple[ProcurementLotRecord, dict[str, Any]]], int]:
    limit = max(0, end_row - start_row)
    statement = _build_procurement_lots_statement(grid_filter=grid_filter)
    total = await _count_procurement_lots(session, statement)
    if limit <= 0:
        return [], total
    records = (
        (
            await session.execute(
                _apply_record_sort(statement, sort_model=sort_model)
                .offset(max(0, start_row))
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [(record, build_procurement_grid_row(record)) for record in records], total


async def summarize_procurement_lots_for_grid(
    session: AsyncSession,
    *,
    grid_filter: dict[str, Any] | None = None,
) -> ProcurementLotsGridSummary:
    statement = _build_procurement_lots_statement(grid_filter=grid_filter)
    subquery = statement.order_by(None).subquery()
    total, new_count, relevant_count, high_score_count, decision_pending_count = (
        await session.execute(
            select(
                func.count(),
                func.count().filter(subquery.c.is_new.is_(True)),
                func.count().filter(subquery.c.category.is_not(None), subquery.c.excluded_keywords == []),
                func.count().filter(subquery.c.attractiveness_score >= 75),
                func.count().filter(subquery.c.workflow_status == "decision"),
            )
        )
    ).one()
    return ProcurementLotsGridSummary(
        total=int(total or 0),
        new_count=int(new_count or 0),
        relevant_count=int(relevant_count or 0),
        high_score_count=int(high_score_count or 0),
        decision_pending_count=int(decision_pending_count or 0),
    )


async def list_procurement_lot_column_histogram(
    session: AsyncSession,
    *,
    column_id: str,
    histogram_options: dict[str, Any] | None = None,
    sort_model: list[dict[str, str]] | None = None,
    grid_filter: dict[str, Any] | None = None,
) -> list[LotDatagridHistogramEntry]:
    expression, value_type = _grid_column_expression(column_id)
    if expression is None:
        return []
    options = histogram_options or {}
    limit = _histogram_limit(options.get("limit"))
    statement = _build_procurement_lots_statement(grid_filter=grid_filter)
    base = statement.order_by(None).subquery()
    base_expression = getattr(base.c, _column_key_for_expression(column_id), None)
    expression = base_expression if base_expression is not None else expression
    histogram_statement = (
        select(expression.label("value"), func.count().label("count"))
        .select_from(base)
        .group_by(expression)
        .order_by(func.count().desc(), expression.asc().nulls_last())
        .limit(limit)
    )
    del sort_model
    rows = (await session.execute(histogram_statement)).all()
    return [
        LotDatagridHistogramEntry(
            token=_serialize_histogram_token(row.value, value_type),
            value=_histogram_json_value(row.value),
            count=int(row.count or 0),
            text=_histogram_text_value(row.value),
        )
        for row in rows
    ]


def build_procurement_grid_row(record: ProcurementLotRecord) -> dict[str, Any]:
    return {
        "id": procurement_lot_grid_row_id(record),
        "recordId": record.id,
        "source": record.source_code,
        "externalId": record.external_id,
        "registryNumber": record.registry_number,
        "law": record.law,
        "title": record.title,
        "status": record.status,
        "customerName": record.customer_name,
        "customerInn": record.customer_inn,
        "organizerName": record.organizer_name,
        "procedureType": record.procedure_type,
        "platformName": record.platform_name,
        "region": record.region,
        "deliveryRegion": record.delivery_region,
        "deliveryAddress": record.delivery_address,
        "initialPrice": _decimal_json(record.initial_price_value),
        "initialPriceText": record.initial_price,
        "currency": record.currency,
        "publicationDate": _datetime_json(record.publication_at),
        "applicationDeadline": _datetime_json(record.application_deadline_at),
        "noticeUrl": record.notice_url,
        "documentsUrl": record.documents_url,
        "specificationUrl": record.specification_url,
        "certificateRequirements": record.certificate_requirements,
        "documentationPresent": record.documentation_present,
        "isNew": record.is_new,
        "category": record.category,
        "matchedKeywords": list(record.matched_keywords or []),
        "excludedKeywords": list(record.excluded_keywords or []),
        "filterReason": record.filter_reason,
        "score": record.attractiveness_score,
        "scoreLevel": record.attractiveness_level,
        "scoreReasons": list(record.attractiveness_reasons or []),
        "scoringVersion": record.scoring_version,
        "scoringInputHash": record.scoring_input_hash,
        "scoredAt": _datetime_json(record.scored_at),
        "workflowStatus": record.workflow_status,
        "assignee": record.assignee,
        "comment": record.comment,
        "finalDecision": record.final_decision,
        "rejectionReason": record.rejection_reason,
        "bidSecurityAmount": _decimal_json(record.bid_security_amount),
        "contractSecurityAmount": _decimal_json(record.contract_security_amount),
        "prepaymentPercent": _decimal_json(record.prepayment_percent),
        "paymentTerms": record.payment_terms,
        "quantity": _decimal_json(record.quantity),
        "unitNmck": _decimal_json(record.unit_nmck),
        "costRealistic": _decimal_json(record.cost_realistic),
        "costCautious": _decimal_json(record.cost_cautious),
        "netProfit": _decimal_json(record.net_profit),
        "profitability": _decimal_json(record.profitability),
        "roi": _decimal_json(record.roi),
        "cashGapPeak": _decimal_json(record.cash_gap_peak),
        "calculatorInputs": dict(record.calculator_inputs or {}),
        "calculatorScenarios": dict(record.calculator_scenarios or {}),
        "firstSeenAt": _datetime_json(record.first_seen_at),
        "lastSeenAt": _datetime_json(record.last_seen_at),
        "lifecycleStatus": record.lifecycle_status or "active",
        "finishedAt": _datetime_json(record.finished_at),
        "archivedAt": _datetime_json(record.archived_at),
        "archiveReason": record.archive_reason,
        "actualityCheckedAt": _datetime_json(record.actuality_checked_at),
    }


def _build_procurement_lots_statement(*, grid_filter: dict[str, Any] | None = None):
    statement = select(ProcurementLotRecord).where(
        or_(
            ProcurementLotRecord.lifecycle_status == "active",
            ProcurementLotRecord.lifecycle_status.is_(None),
        )
    )
    predicate = _grid_filter_predicate(grid_filter)
    if predicate is not None:
        statement = statement.where(predicate)
    return statement


async def _count_procurement_lots(session: AsyncSession, statement) -> int:
    return int(await session.scalar(select(func.count()).select_from(statement.order_by(None).subquery())) or 0)


def _apply_record_sort(statement, *, sort_model: list[dict[str, str]] | None = None):
    order_by = []
    for entry in (sort_model or [])[:5]:
        expression, _ = _grid_column_expression(entry["key"])
        if expression is None:
            continue
        ordered = expression.desc() if entry["direction"] == "desc" else expression.asc()
        order_by.append(ordered.nulls_last())
    if not order_by:
        order_by = [ProcurementLotRecord.attractiveness_score.desc().nulls_last(), ProcurementLotRecord.publication_at.desc().nulls_last()]
    return statement.order_by(*order_by, ProcurementLotRecord.source_code.asc(), ProcurementLotRecord.external_id.asc(), ProcurementLotRecord.id.asc())


def _merge_query_options_into_filter_model(
    filter_model: dict[str, Any] | None,
    request: ProcurementLotsGridQueryOptions,
) -> dict[str, Any] | None:
    expression = _query_options_advanced_expression(request)
    if expression is None:
        return filter_model
    next_filter_model = dict(filter_model or {})
    current_expression = next_filter_model.get("advancedExpression")
    next_filter_model["advancedExpression"] = (
        {"kind": "group", "operator": "and", "children": [current_expression, expression]}
        if isinstance(current_expression, dict)
        else expression
    )
    return next_filter_model


def _query_options_advanced_expression(request: ProcurementLotsGridQueryOptions) -> dict[str, Any] | None:
    conditions: list[dict[str, Any]] = []
    _append_text_condition(conditions, "source", "equals", request.source if request.source != "all" else None)
    _append_text_condition(conditions, "law", "equals", request.law)
    _append_text_condition(conditions, "status", "contains", request.status)
    _append_text_condition(conditions, "workflowStatus", "equals", request.workflow_status)
    _append_text_condition(conditions, "assignee", "equals", request.assignee)
    _append_text_condition(conditions, "category", "equals", request.category)
    _append_decimal_condition(conditions, "initialPrice", "gte", request.min_price)
    _append_decimal_condition(conditions, "initialPrice", "lte", request.max_price)
    if request.min_score is not None:
        conditions.append({"kind": "condition", "key": "score", "operator": "gte", "value": request.min_score})
    if request.only_new:
        conditions.append({"kind": "condition", "key": "isNew", "operator": "equals", "value": True})
    if not conditions:
        return None
    return conditions[0] if len(conditions) == 1 else {"kind": "group", "operator": "and", "children": conditions}


def _grid_filter_predicate(grid_filter: dict[str, Any] | None):
    if not grid_filter:
        return None
    predicates = []
    column_filters = grid_filter.get("columnFilters")
    if isinstance(column_filters, dict):
        for key, payload in column_filters.items():
            predicate = _column_filter_predicate(str(key), payload)
            if predicate is not None:
                predicates.append(predicate)
    advanced_expression = grid_filter.get("advancedExpression")
    predicate = _advanced_expression_predicate(advanced_expression)
    if predicate is not None:
        predicates.append(predicate)
    quick_filter = grid_filter.get("quickFilter")
    predicate = _quick_filter_predicate(quick_filter)
    if predicate is not None:
        predicates.append(predicate)
    return and_(*predicates) if predicates else None


def _column_filter_predicate(key: str, payload):
    if not isinstance(payload, dict):
        return None
    if payload.get("kind") == "valueSet":
        tokens = payload.get("tokens")
        expression, _ = _grid_column_expression(key)
        if expression is None or not isinstance(tokens, list) or not tokens:
            return None
        return _value_set_tokens_predicate(expression, [str(token) for token in tokens])
    if payload.get("kind") == "predicate":
        return _predicate_filter_condition(key, payload.get("operator"), payload.get("value"), payload.get("value2"), payload.get("caseSensitive"))
    return None


def _advanced_expression_predicate(payload):
    if not isinstance(payload, dict):
        return None
    kind = payload.get("kind")
    if kind == "condition":
        return _predicate_filter_condition(payload.get("key"), payload.get("operator"), payload.get("value"), payload.get("value2"), False)
    if kind == "group":
        children = [_advanced_expression_predicate(child) for child in payload.get("children") or []]
        predicates = [predicate for predicate in children if predicate is not None]
        if not predicates:
            return None
        return or_(*predicates) if payload.get("operator") == "or" else and_(*predicates)
    if kind == "not":
        child = _advanced_expression_predicate(payload.get("child"))
        return not_(child) if child is not None else None
    return None


def _predicate_filter_condition(key, operator, value=None, value2=None, case_sensitive=False):
    operator = _normalize_filter_operator(operator)
    expression, value_type = _grid_column_expression(str(key) if key else None)
    if expression is None:
        return None
    text_expression = cast(expression, String)
    if operator in {"contains", "startsWith", "endsWith"}:
        if value is None or len(str(value).strip()) < 2:
            return None
        pattern_value = _escape_like(str(value).strip())
        compared_text = text_expression if case_sensitive else func.lower(text_expression)
        compared_value = pattern_value if case_sensitive else pattern_value.lower()
        if operator == "contains":
            return compared_text.like(f"%{compared_value}%", escape="\\")
        if operator == "startsWith":
            return compared_text.like(f"{compared_value}%", escape="\\")
        return compared_text.like(f"%{compared_value}", escape="\\")
    normalized_value = _coerce_filter_value(value, value_type)
    normalized_value2 = _coerce_filter_value(value2, value_type)
    comparable_expression = expression if value_type in {"number", "boolean", "datetime"} else text_expression
    if operator == "isNull":
        return expression.is_(None)
    if operator == "notNull":
        return expression.is_not(None)
    if operator == "isEmpty":
        return or_(expression.is_(None), text_expression == "")
    if operator == "notEmpty":
        return and_(expression.is_not(None), text_expression != "")
    if operator == "between" and normalized_value is not None and normalized_value2 is not None:
        return and_(comparable_expression >= normalized_value, comparable_expression <= normalized_value2)
    if operator == "in":
        values = _coerce_filter_list_value(value, value_type)
        if values and value_type == "text":
            return func.lower(text_expression).in_([str(item).lower() for item in values])
        return comparable_expression.in_(values) if values else None
    if normalized_value is None:
        return None
    if operator == "gt":
        return comparable_expression > normalized_value
    if operator == "gte":
        return comparable_expression >= normalized_value
    if operator == "lt":
        return comparable_expression < normalized_value
    if operator == "lte":
        return comparable_expression <= normalized_value
    if operator == "equals":
        return comparable_expression == normalized_value
    if operator == "notEquals":
        return comparable_expression != normalized_value
    return None


def _quick_filter_predicate(payload):
    if not isinstance(payload, dict):
        return None
    query = payload.get("query")
    if query is None or not str(query).strip():
        return None
    terms = [term for term in str(query).strip().lower().split() if term]
    columns = payload.get("columns")
    column_keys = [str(column) for column in columns if isinstance(column, str)] if isinstance(columns, list) else list(DEFAULT_QUICK_FILTER_COLUMNS)
    expressions = [_quick_filter_text_expression(column_key) for column_key in column_keys]
    expressions = [expression for expression in expressions if expression is not None]
    if not expressions:
        return None
    return and_(
        *[
            or_(*(expression.like(f"%{_escape_like(term)}%", escape="\\") for expression in expressions))
            for term in terms
        ]
    )


def _quick_filter_text_expression(key: str):
    expression, _ = _grid_column_expression(key)
    return func.lower(func.coalesce(cast(expression, String), "")) if expression is not None else None


def _grid_filter_has_quick_filter(filter_model: dict[str, Any] | None) -> bool:
    if not isinstance(filter_model, dict):
        return False
    quick_filter = filter_model.get("quickFilter")
    return isinstance(quick_filter, dict) and quick_filter.get("query") is not None and bool(str(quick_filter.get("query")).strip())


def _grid_column_expression(key: str | None):
    if not key:
        return None, "text"
    normalized_key = GRID_COLUMN_ALIASES.get(key, key)
    return {
        "applicationDeadline": (ProcurementLotRecord.application_deadline_at, "datetime"),
        "assignee": (ProcurementLotRecord.assignee, "text"),
        "category": (ProcurementLotRecord.category, "text"),
        "cashGapPeak": (ProcurementLotRecord.cash_gap_peak, "number"),
        "contractSecurityAmount": (ProcurementLotRecord.contract_security_amount, "number"),
        "customerInn": (ProcurementLotRecord.customer_inn, "text"),
        "customerName": (ProcurementLotRecord.customer_name, "text"),
        "deliveryRegion": (ProcurementLotRecord.delivery_region, "text"),
        "externalId": (ProcurementLotRecord.external_id, "text"),
        "filterReason": (ProcurementLotRecord.filter_reason, "text"),
        "finalDecision": (ProcurementLotRecord.final_decision, "text"),
        "id": (ProcurementLotRecord.external_id, "text"),
        "initialPrice": (ProcurementLotRecord.initial_price_value, "number"),
        "isNew": (ProcurementLotRecord.is_new, "boolean"),
        "law": (ProcurementLotRecord.law, "text"),
        "lifecycleStatus": (ProcurementLotRecord.lifecycle_status, "text"),
        "netProfit": (ProcurementLotRecord.net_profit, "number"),
        "platformName": (ProcurementLotRecord.platform_name, "text"),
        "procedureType": (ProcurementLotRecord.procedure_type, "text"),
        "profitability": (ProcurementLotRecord.profitability, "number"),
        "publicationDate": (ProcurementLotRecord.publication_at, "datetime"),
        "registryNumber": (ProcurementLotRecord.registry_number, "text"),
        "region": (ProcurementLotRecord.region, "text"),
        "roi": (ProcurementLotRecord.roi, "number"),
        "score": (ProcurementLotRecord.attractiveness_score, "number"),
        "scoreLevel": (ProcurementLotRecord.attractiveness_level, "text"),
        "source": (ProcurementLotRecord.source_code, "text"),
        "status": (ProcurementLotRecord.status, "text"),
        "title": (ProcurementLotRecord.title, "text"),
        "workflowStatus": (ProcurementLotRecord.workflow_status, "text"),
    }.get(normalized_key, (None, "text"))


def _column_key_for_expression(column_id: str) -> str:
    expression, _ = _grid_column_expression(column_id)
    if hasattr(expression, "key"):
        return str(expression.key)
    return column_id


def _normalize_sort_model(sort_model: list[dict[str, Any]] | None) -> list[dict[str, str]] | None:
    normalized: list[dict[str, str]] = []
    for item in sort_model or []:
        key = _first_string(item, "key", "colId", "columnId", "field")
        direction = _first_string(item, "direction", "sort")
        if key and direction in {"asc", "desc"}:
            normalized.append({"key": key, "direction": direction})
    return normalized or None


def _histogram_filter_model(filter_model: dict[str, Any] | None, column_id: str, options: dict[str, Any]) -> dict[str, Any] | None:
    if not filter_model or options.get("ignoreSelfFilter") is not True:
        return filter_model
    filtered = dict(filter_model)
    column_filters = dict(filtered.get("columnFilters") or {})
    column_filters.pop(column_id, None)
    filtered["columnFilters"] = column_filters
    return filtered


def _append_text_condition(conditions: list[dict[str, Any]], key: str, operator: str, value: str | None) -> None:
    if value is not None and str(value).strip():
        conditions.append({"kind": "condition", "key": key, "operator": operator, "value": str(value).strip()})


def _append_decimal_condition(conditions: list[dict[str, Any]], key: str, operator: str, value: Decimal | None) -> None:
    if value is not None:
        conditions.append({"kind": "condition", "key": key, "operator": operator, "value": str(value)})


def _normalize_filter_operator(operator):
    if not isinstance(operator, str):
        return operator
    return {
        "starts-with": "startsWith",
        "ends-with": "endsWith",
        "not-equals": "notEquals",
        "is-null": "isNull",
        "not-null": "notNull",
        "is-empty": "isEmpty",
        "not-empty": "notEmpty",
    }.get(operator, operator)


def _coerce_filter_value(value, value_type: str):
    if value is None:
        return None
    if value_type == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "да"}
    if value_type == "number":
        try:
            return Decimal(str(value).replace(" ", "").replace(",", "."))
        except (DecimalException, ValueError):
            return None
    return str(value) if value_type == "text" else value


def _coerce_filter_list_value(value, value_type: str):
    raw_values = value if isinstance(value, list) else str(value).split(",")
    values = []
    for item in raw_values:
        normalized = _coerce_filter_value(str(item).strip() if item is not None else None, value_type)
        if normalized is not None and normalized not in values:
            values.append(normalized)
    return values


def _value_set_tokens_predicate(expression, tokens: list[str]):
    predicates = []
    string_values = [token.removeprefix("string:").lower() for token in tokens if token.startswith("string:")]
    number_values = []
    boolean_values = []
    include_null = "null" in tokens
    for token in tokens:
        if token.startswith("number:"):
            try:
                number_values.append(Decimal(token.removeprefix("number:")))
            except (DecimalException, ValueError):
                continue
        if token.startswith("boolean:"):
            raw = token.removeprefix("boolean:").strip().lower()
            if raw in {"true", "false"}:
                boolean_values.append(raw == "true")
    if include_null:
        predicates.append(expression.is_(None))
    if string_values:
        predicates.append(func.lower(cast(expression, String)).in_(string_values))
    if number_values:
        predicates.append(expression.in_(number_values))
    if boolean_values:
        predicates.append(expression.in_(boolean_values))
    return or_(*predicates) if predicates else None


def _histogram_limit(value: object) -> int:
    try:
        return min(250, max(1, int(value or 50)))
    except (TypeError, ValueError):
        return 50


def _serialize_histogram_token(value: object, value_type: str) -> str:
    if value is None:
        return "null"
    if value_type == "boolean" or isinstance(value, bool):
        return f"boolean:{str(bool(value)).lower()}"
    if value_type == "number" or isinstance(value, int | float | Decimal):
        return f"number:{value}"
    return f"string:{_histogram_text_value(value)}"


def _histogram_json_value(value: object) -> object:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _histogram_text_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _decimal_json(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _datetime_json(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _first_string(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
