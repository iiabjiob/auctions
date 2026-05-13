from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.scoring_profile import LotScoringProfile


NotificationPriorityThreshold = Literal["urgent", "high", "medium", "low"]


class UserInterestProfileBase(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    profile_payload: dict = Field(default_factory=dict)
    min_rating: int = Field(default=0, ge=0, le=100)
    notification_priority_threshold: NotificationPriorityThreshold | None = "medium"
    telegram_enabled: bool = True
    is_active: bool = True

    @field_validator("profile_payload")
    @classmethod
    def validate_profile_payload(cls, value: dict) -> dict:
        return LotScoringProfile.model_validate(value).canonical_payload()


class UserInterestProfileCreate(UserInterestProfileBase):
    pass


class UserInterestProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    profile_payload: dict | None = None
    min_rating: int | None = Field(default=None, ge=0, le=100)
    notification_priority_threshold: NotificationPriorityThreshold | None = None
    telegram_enabled: bool | None = None
    is_active: bool | None = None

    @field_validator("profile_payload")
    @classmethod
    def validate_profile_payload(cls, value: dict | None) -> dict | None:
        if value is None:
            return None
        return LotScoringProfile.model_validate(value).canonical_payload()


class UserInterestProfileResponse(UserInterestProfileBase):
    id: str
    owner_user_id: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
