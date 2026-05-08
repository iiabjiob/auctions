from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class DecisionLevel(StrEnum):
    IGNORE = "ignore"
    WATCH = "watch"
    INSPECT = "inspect"
    CALCULATE = "calculate"
    BID_CANDIDATE = "bid_candidate"


class ActionRecommendation(StrEnum):
    IGNORE = "ignore"
    MONITOR = "monitor"
    REQUEST_DOCS = "request_docs"
    INSPECT = "inspect"
    CALCULATE_MAX_BID = "calculate_max_bid"
    PREPARE_BID = "prepare_bid"


class LotDecisionReason(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    message: str
    source: str | None = None


class LotDecisionRisk(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    message: str
    level: Literal["low", "medium", "high"] = "medium"


class LotDecisionNextAction(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    action: ActionRecommendation
    label: str
    deadline: str | None = None


class LotEconomicsDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    current_price: Decimal | None = None
    market_value: Decimal | None = None
    expected_costs: Decimal = Decimal("0")
    target_roi: Decimal
    max_buy_price: Decimal | None = None
    estimated_profit: Decimal | None = None
    confidence: Literal["low", "medium", "high"] = "low"
    missing_inputs: tuple[str, ...] = Field(default_factory=tuple)


class LotDecisionReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    auction_id: str
    lot_id: str
    record_id: int

    title: str | None = None
    source_title: str | None = None
    region: str | None = None
    current_price: str | None = None
    deadline: str | None = None

    rating_score: int = Field(ge=0, le=100)
    rating_level: str

    profile_hash: str | None = None
    profile_fit_summary: str | None = None
    economics: LotEconomicsDecision | None = None

    decision_level: DecisionLevel
    recommendation: ActionRecommendation
    reasons: tuple[LotDecisionReason, ...] = Field(default_factory=tuple)
    risks: tuple[LotDecisionRisk, ...] = Field(default_factory=tuple)
    next_actions: tuple[LotDecisionNextAction, ...] = Field(default_factory=tuple)
    generated_at: datetime

    def canonical_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


def lot_decision_report_canonical_json(report: LotDecisionReport) -> str:
    return json.dumps(report.canonical_payload(), sort_keys=True, ensure_ascii=False)


def build_lot_decision_report_hash(report: LotDecisionReport) -> str:
    return hashlib.sha256(
        lot_decision_report_canonical_json(report).encode("utf-8")
    ).hexdigest()
