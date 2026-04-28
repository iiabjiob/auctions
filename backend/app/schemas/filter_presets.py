from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class FilterPresetBase(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    filters: dict = Field(default_factory=dict)
    grid_view: dict | None = None
    is_favorite: bool = False


class FilterPresetCreate(FilterPresetBase):
    pass


class FilterPresetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    filters: dict | None = None
    grid_view: dict | None = None
    is_favorite: bool | None = None


class FilterPresetResponse(FilterPresetBase):
    id: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
