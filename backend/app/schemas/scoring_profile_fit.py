from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LotProfileFitDimension(BaseModel):
    model_config = ConfigDict(extra="forbid")

    available: bool = False
    matched: bool | None = None
    reasons: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)


class LotProfileFitEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_identifier: str | None = None
    matches_profile: bool
    dimensions: dict[str, LotProfileFitDimension] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
