from __future__ import annotations

from decimal import Decimal
from typing import Literal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.auctions import LotDatagridHistogramEntry, LotDatagridRow


class AuctionLotsGridRange(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    start_row: int = Field(ge=0, alias="startRow")
    end_row: int = Field(ge=0, alias="endRow")


class AuctionLotsGridQueryOptions(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    period: str = Field(default="month", pattern="^(week|month|year)$")
    source: str | None = None
    status: str | None = None
    analysis_color: str | None = None
    min_price: Decimal | None = None
    max_price: Decimal | None = None
    only_new: bool = False
    shortlist: bool = False
    min_rating: int | None = Field(default=None, ge=0, le=100)
    sort_model: list[dict[str, Any]] = Field(default_factory=list, alias="sortModel")
    filter_model: dict[str, Any] | None = Field(default=None, alias="filterModel")


class AuctionLotsGridPullRequest(AuctionLotsGridQueryOptions):
    start_row: int | None = Field(default=None, ge=0, alias="startRow")
    end_row: int | None = Field(default=None, ge=0, alias="endRow")
    range_: AuctionLotsGridRange | None = Field(default=None, alias="range")

    @model_validator(mode="after")
    def validate_range(self) -> "AuctionLotsGridPullRequest":
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


class AuctionLotsGridPullRow(BaseModel):
    id: str
    index: int
    row: LotDatagridRow


class AuctionLotsGridSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    total: int = 0
    new_count: int = Field(default=0, alias="newCount")
    open_applications_count: int = Field(default=0, alias="openApplicationsCount")
    high_rating_count: int = Field(default=0, alias="highRatingCount")


class AuctionLotsGridPullResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    rows: list[AuctionLotsGridPullRow]
    total: int
    dataset_version: int = Field(alias="datasetVersion")
    summary: AuctionLotsGridSummary = Field(default_factory=AuctionLotsGridSummary)


class AuctionLotsGridHistogramRequest(AuctionLotsGridQueryOptions):
    column_id: str = Field(alias="columnId")
    options: dict[str, Any] = Field(default_factory=dict)


class AuctionLotsGridHistogramResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    column_id: str = Field(alias="columnId")
    entries: list[LotDatagridHistogramEntry]


class AuctionLotsGridCellEdit(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    row_id: str = Field(alias="rowId")
    column_id: str = Field(alias="columnId")
    value: Any = None


class AuctionLotsGridEditRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    base_version: int = Field(alias="baseVersion", ge=0)
    edits: list[AuctionLotsGridCellEdit] = Field(min_length=1)


class AuctionLotsGridEditResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    dataset_version: int = Field(alias="datasetVersion")
    updated_rows: list[AuctionLotsGridPullRow] = Field(alias="updatedRows")


class AuctionLotsGridFillRange(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    start_row: int = Field(ge=0, alias="startRow")
    end_row: int = Field(ge=0, alias="endRow")
    column_id: str = Field(alias="columnId", min_length=1)


class AuctionLotsGridFillRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    base_version: int = Field(alias="baseVersion", ge=0)
    source: AuctionLotsGridFillRange
    target: AuctionLotsGridFillRange
    mode: Literal["copy"]
