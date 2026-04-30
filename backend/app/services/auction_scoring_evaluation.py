from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.models.auction import AuctionLotDetailCache, AuctionLotRecord, AuctionLotWorkItem
from app.schemas.analysis_config import OwnerScoringProfile, ScoringDimensionWeights
from app.schemas.auctions import LotDatagridRow, LotFreshness, LotRating
from app.services.auction_scoring import SCORING_VERSION, recalculate_record_rating


def load_scoring_golden_cases(path: Path | str) -> list[dict[str, Any]]:
    with Path(path).open(encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, list):
        raise ValueError("Golden scoring fixtures must be a JSON array")
    return [case for case in payload if isinstance(case, dict)]


def build_scoring_regression_report(
    cases: list[dict[str, Any]],
    *,
    owner_profile: OwnerScoringProfile | None = None,
    dimension_weights: ScoringDimensionWeights | None = None,
    ai_scores: dict[str, int] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    evaluated_cases = [
        _evaluate_case(
            case,
            index=index,
            owner_profile=owner_profile,
            dimension_weights=dimension_weights,
            now=now,
        )
        for index, case in enumerate(cases, start=1)
    ]
    ranked_cases = sorted(evaluated_cases, key=lambda item: (-item["score"], item["case_id"]))
    ranking = []
    for current_rank, item in enumerate(ranked_cases, start=1):
        baseline_rank = item.get("baseline_rank")
        ranking.append(
            {
                "case_id": item["case_id"],
                "label": item["label"],
                "review_bucket": item["review_bucket"],
                "baseline_rank": baseline_rank,
                "current_rank": current_rank,
                "rank_delta": current_rank - baseline_rank if isinstance(baseline_rank, int) else None,
                "score": item["score"],
                "level": item["level"],
                "cap_keys": item["cap_keys"],
            }
        )

    failures = [failure for item in evaluated_cases for failure in item["failures"]]
    return {
        "scoring_version": SCORING_VERSION,
        "summary": {
            "total": len(evaluated_cases),
            "passed": len(evaluated_cases) - sum(1 for item in evaluated_cases if item["failures"]),
            "failed": sum(1 for item in evaluated_cases if item["failures"]),
            "failure_count": len(failures),
        },
        "ranking": ranking,
        "ai_rank_comparison": _compare_evaluation_ai_ranks(ranking, ai_scores or {}),
        "cases": evaluated_cases,
        "failures": failures,
    }


def _compare_evaluation_ai_ranks(ranking: list[dict[str, Any]], ai_scores: dict[str, int]) -> list[dict[str, Any]]:
    if not ai_scores:
        return []
    deterministic_rows = [row for row in ranking if row["case_id"] in ai_scores]
    ai_ranked = sorted(deterministic_rows, key=lambda row: (-ai_scores[row["case_id"]], row["current_rank"]))
    ai_ranks = {row["case_id"]: rank for rank, row in enumerate(ai_ranked, start=1)}
    return [
        {
            "case_id": row["case_id"],
            "deterministic_score": row["score"],
            "deterministic_rank": row["current_rank"],
            "ai_score": ai_scores[row["case_id"]],
            "ai_rank": ai_ranks[row["case_id"]],
            "rank_delta": ai_ranks[row["case_id"]] - row["current_rank"],
        }
        for row in deterministic_rows
    ]


def _evaluate_case(
    case: dict[str, Any],
    *,
    index: int,
    owner_profile: OwnerScoringProfile | None,
    dimension_weights: ScoringDimensionWeights | None,
    now: datetime | None,
) -> dict[str, Any]:
    record = _build_record(case, index=index, now=now)
    detail_cache = _build_detail_cache(case, record_id=index, now=now)
    work_item = _build_work_item(case, record_id=index)
    rating = recalculate_record_rating(
        record,
        detail_cache,
        work_item,
        owner_profile=owner_profile,
        dimension_weights=dimension_weights,
    )
    cap_keys = [cap["key"] for cap in record.score_breakdown.get("caps", [])]
    failures = _validate_case_expectations(case, rating=rating, cap_keys=cap_keys)
    return {
        "case_id": str(case.get("id") or f"case-{index}"),
        "label": str(case.get("label") or case.get("lot_name") or f"Case {index}"),
        "review_bucket": str(case.get("review_bucket") or "uncategorized"),
        "baseline_rank": _optional_int(case.get("baseline_rank")),
        "score": rating.score,
        "level": rating.level,
        "reasons": rating.reasons,
        "cap_keys": cap_keys,
        "score_breakdown": record.score_breakdown,
        "failures": failures,
    }


def _build_record(case: dict[str, Any], *, index: int, now: datetime | None) -> AuctionLotRecord:
    case_id = str(case.get("id") or f"case-{index}")
    lot_name = str(case.get("lot_name") or case_id)
    status = str(case.get("status") or "Идет прием заявок")
    current_price = _money_text(case.get("current_price"))
    current_price_value = _decimal_or_none(case.get("current_price"))
    application_deadline = _application_deadline(case, now=now)
    row = LotDatagridRow(
        row_id=f"golden:auction-{index}:lot-{index}",
        source="golden",
        source_title="Golden fixtures",
        auction_id=f"auction-{index}",
        auction_number=f"G-{index}",
        lot_id=f"lot-{index}",
        lot_number=str(index),
        lot_name=lot_name,
        lot_description=str(case.get("description") or "") or None,
        category=str(case.get("category") or "") or None,
        location=str(case.get("region") or "") or None,
        location_region=str(case.get("region") or "") or None,
        status=status,
        initial_price=current_price,
        initial_price_value=current_price_value,
        current_price=current_price,
        current_price_value=current_price_value,
        application_deadline=application_deadline,
        market_value=_decimal_or_none(case.get("market_value")),
        target_profit=_decimal_or_none(case.get("target_profit")),
        freshness=LotFreshness(is_new=True),
        rating=LotRating(score=0, level="low", reasons=[]),
    )
    return AuctionLotRecord(
        id=index,
        source_code="golden",
        auction_external_id=f"auction-{index}",
        lot_external_id=f"lot-{index}",
        auction_number=f"G-{index}",
        lot_number=str(index),
        lot_name=lot_name,
        status=status,
        initial_price=current_price,
        content_hash=f"golden-{case_id}",
        datagrid_row=row.model_dump(mode="json"),
        normalized_item={
            "auction": {"application_deadline": application_deadline},
            "lot": {
                "name": lot_name,
                "status": status,
                "current_price": current_price,
                "category": case.get("category"),
                "region": case.get("region"),
                "description": case.get("description"),
            },
        },
    )


def _build_detail_cache(case: dict[str, Any], *, record_id: int, now: datetime | None) -> AuctionLotDetailCache:
    documents = [{"name": name} for name in case.get("documents", []) if isinstance(name, str)]
    return AuctionLotDetailCache(
        lot_record_id=record_id,
        content_hash=f"golden-detail-{record_id}",
        lot_detail={
            "lot": {
                "description": case.get("description"),
                "inspection_order": case.get("inspection_order"),
                "current_price": _money_text(case.get("current_price")),
                "market_value": _money_text(case.get("market_value")),
                "category": case.get("category"),
                "region": case.get("region"),
            }
        },
        auction_detail={"auction": {"application_deadline": _application_deadline(case, now=now)}},
        documents=documents,
    )


def _build_work_item(case: dict[str, Any], *, record_id: int) -> AuctionLotWorkItem:
    return AuctionLotWorkItem(
        lot_record_id=record_id,
        decision_status=case.get("decision_status"),
        market_value=_decimal_or_none(case.get("market_value")),
        platform_fee=_decimal_or_zero(case.get("platform_fee")),
        delivery_cost=_decimal_or_zero(case.get("delivery_cost")),
        dismantling_cost=_decimal_or_zero(case.get("dismantling_cost")),
        repair_cost=_decimal_or_zero(case.get("repair_cost")),
        storage_cost=_decimal_or_zero(case.get("storage_cost")),
        legal_cost=_decimal_or_zero(case.get("legal_cost")),
        other_costs=_decimal_or_zero(case.get("other_costs")),
        target_profit=_decimal_or_none(case.get("target_profit")),
        analogs=[],
    )


def _validate_case_expectations(case: dict[str, Any], *, rating: LotRating, cap_keys: list[str]) -> list[dict[str, Any]]:
    expected = case.get("expected") if isinstance(case.get("expected"), dict) else {}
    failures: list[dict[str, Any]] = []
    if expected.get("level") and rating.level != expected["level"]:
        failures.append(_failure(case, "level", expected["level"], rating.level))
    if expected.get("score_min") is not None and rating.score < int(expected["score_min"]):
        failures.append(_failure(case, "score_min", expected["score_min"], rating.score))
    if expected.get("score_max") is not None and rating.score > int(expected["score_max"]):
        failures.append(_failure(case, "score_max", expected["score_max"], rating.score))
    for cap_key in expected.get("required_cap_keys", []):
        if cap_key not in cap_keys:
            failures.append(_failure(case, "required_cap_key", cap_key, cap_keys))
    for cap_key in expected.get("forbidden_cap_keys", []):
        if cap_key in cap_keys:
            failures.append(_failure(case, "forbidden_cap_key", cap_key, cap_keys))
    return failures


def _failure(case: dict[str, Any], check: str, expected: Any, actual: Any) -> dict[str, Any]:
    return {
        "case_id": case.get("id"),
        "check": check,
        "expected": expected,
        "actual": actual,
    }


def _application_deadline(case: dict[str, Any], *, now: datetime | None = None) -> str | None:
    if case.get("application_deadline"):
        return str(case["application_deadline"])
    hours = _optional_int(case.get("application_deadline_hours_from_now"))
    if hours is None:
        return None
    base = (now or datetime.now(UTC)).replace(tzinfo=None)
    return (base + timedelta(hours=hours)).strftime("%d.%m.%Y %H:%M")


def _money_text(value: Any) -> str | None:
    parsed = _decimal_or_none(value)
    return f"{parsed} руб." if parsed is not None else None


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def _decimal_or_zero(value: Any) -> Decimal:
    return _decimal_or_none(value) or Decimal("0")


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)
