from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from collections.abc import Iterable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LotScoringProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    profile_identifier: str | None = None
    target_regions: list[str] = Field(default_factory=list)
    target_categories: list[str] = Field(default_factory=list)
    budget_min: Decimal | None = None
    budget_max: Decimal | None = None
    minimum_roi: Decimal | None = None
    minimum_discount: Decimal | None = None
    allowed_legal_risks: list[str] = Field(default_factory=list)
    max_distance_km: Decimal | None = None
    stop_words: list[str] = Field(default_factory=list)
    desired_keywords: list[str] = Field(default_factory=list)
    strategy: Literal["conservative", "balanced", "aggressive"] = "balanced"
    weights: dict[str, Decimal] = Field(default_factory=dict)

    def canonical_payload(self) -> dict[str, object]:
        return {
            "profile_identifier": _normalize_text(self.profile_identifier),
            "target_regions": _normalize_text_list(self.target_regions),
            "target_categories": _normalize_text_list(self.target_categories),
            "budget_min": _normalize_decimal(self.budget_min),
            "budget_max": _normalize_decimal(self.budget_max),
            "minimum_roi": _normalize_decimal(self.minimum_roi),
            "minimum_discount": _normalize_decimal(self.minimum_discount),
            "allowed_legal_risks": _normalize_text_list(_normalize_legal_risk(value) for value in self.allowed_legal_risks),
            "max_distance_km": _normalize_decimal(self.max_distance_km),
            "stop_words": _normalize_text_list(self.stop_words),
            "desired_keywords": _normalize_text_list(self.desired_keywords),
            "strategy": _normalize_text(self.strategy) or "balanced",
            "weights": {key: _normalize_decimal(value) for key, value in sorted(self.weights.items(), key=lambda item: item[0])},
        }


def build_lot_scoring_profile_hash(profile: LotScoringProfile) -> str:
    payload = profile.canonical_payload()
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _normalize_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_text_list(values: Iterable[object] | object) -> list[str]:
    if isinstance(values, (str, bytes, bytearray)) or not isinstance(values, Iterable):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _normalize_text(value)
        if text is None:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(text)
    normalized.sort(key=lambda item: item.casefold())
    return normalized


def _normalize_decimal(value: Decimal | None) -> str | None:
    if value is None:
        return None
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return format(normalized.quantize(Decimal("1")), "f")
    return format(normalized, "f")


def _normalize_legal_risk(value: object) -> str | None:
    text = _normalize_text(value)
    if text is None:
        return None
    return text.casefold()
