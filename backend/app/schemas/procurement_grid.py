from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.auctions import LotDatagridHistogramEntry


class ProcurementLotsGridRange(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    start_row: int = Field(ge=0, alias="startRow")
    end_row: int = Field(ge=0, alias="endRow")


class ProcurementLotsGridQueryOptions(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source: str | None = "zakupki"
    law: str | None = None
    status: str | None = None
    workflow_status: str | None = Field(default=None, alias="workflowStatus")
    assignee: str | None = None
    category: str | None = None
    min_price: Decimal | None = Field(default=None, alias="minPrice")
    max_price: Decimal | None = Field(default=None, alias="maxPrice")
    min_score: int | None = Field(default=None, ge=0, le=100, alias="minScore")
    only_new: bool = Field(default=False, alias="onlyNew")
    sort_model: list[dict[str, Any]] = Field(default_factory=list, alias="sortModel")
    filter_model: dict[str, Any] | None = Field(default=None, alias="filterModel")


class ProcurementLotsGridPullRequest(ProcurementLotsGridQueryOptions):
    start_row: int | None = Field(default=None, ge=0, alias="startRow")
    end_row: int | None = Field(default=None, ge=0, alias="endRow")
    range_: ProcurementLotsGridRange | None = Field(default=None, alias="range")

    @model_validator(mode="after")
    def validate_range(self) -> "ProcurementLotsGridPullRequest":
        if self.range_ is not None:
            self.start_row = self.start_row if self.start_row is not None else self.range_.start_row
            self.end_row = self.end_row if self.end_row is not None else self.range_.end_row
        if self.start_row is None or self.end_row is None:
            raise ValueError("startRow/endRow or range.startRow/range.endRow are required")
        if self.end_row < self.start_row:
            raise ValueError("endRow must be greater than or equal to startRow")
        return self

    @property
    def resolved_start_row(self) -> int:
        return int(self.start_row or 0)

    @property
    def resolved_end_row(self) -> int:
        return int(self.end_row or 0)


class ProcurementLotsGridPullRow(BaseModel):
    id: str
    index: int
    row: dict[str, Any]


class ProcurementLotsGridSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    total: int = 0
    new_count: int = Field(default=0, alias="newCount")
    relevant_count: int = Field(default=0, alias="relevantCount")
    high_score_count: int = Field(default=0, alias="highScoreCount")
    decision_pending_count: int = Field(default=0, alias="decisionPendingCount")


class ProcurementLotsGridPullResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    rows: list[ProcurementLotsGridPullRow]
    total: int
    dataset_version: int = Field(alias="datasetVersion")
    summary: ProcurementLotsGridSummary = Field(default_factory=ProcurementLotsGridSummary)


class ProcurementLotsGridHistogramRequest(ProcurementLotsGridQueryOptions):
    column_id: str = Field(alias="columnId")
    options: dict[str, Any] = Field(default_factory=dict)


class ProcurementLotsGridHistogramResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    column_id: str = Field(alias="columnId")
    entries: list[LotDatagridHistogramEntry]
