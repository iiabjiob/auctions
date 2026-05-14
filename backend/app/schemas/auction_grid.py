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
    include_archived: bool = False
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
    active_count: int = Field(default=0, alias="activeCount")
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

    base_version: int | None = Field(default=None, alias="baseVersion", ge=0)
    base_revision: str | int | None = Field(default=None, alias="baseRevision")
    edits: list[AuctionLotsGridCellEdit] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_base_version(self) -> "AuctionLotsGridEditRequest":
        if self.base_version is None and self.base_revision is not None:
            try:
                self.base_version = int(self.base_revision)
            except (TypeError, ValueError) as error:
                raise ValueError("baseRevision must be an integer revision") from error
        if self.base_version is None:
            raise ValueError("baseVersion or baseRevision is required")
        return self


class AuctionLotsGridEditResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    dataset_version: int = Field(alias="datasetVersion")
    updated_rows: list[AuctionLotsGridPullRow] = Field(alias="updatedRows")
    revision: str | None = None
    committed: list[dict[str, Any]] = Field(default_factory=list)
    rejected: list[dict[str, Any]] = Field(default_factory=list)
    invalidation: dict[str, Any] | None = None
    rows: list[AuctionLotsGridPullRow] = Field(default_factory=list)


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


class AuctionLotsGridFillCommitRange(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    start_row: int = Field(ge=0, alias="startRow")
    end_row: int = Field(ge=0, alias="endRow")
    start_column: int = Field(default=0, ge=0, alias="startColumn")
    end_column: int = Field(default=0, ge=0, alias="endColumn")


class AuctionLotsGridFillCommitRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    operation_id: str | None = Field(default=None, alias="operationId")
    revision: str | int | None = None
    base_revision: str | int | None = Field(default=None, alias="baseRevision")
    projection_hash: str | None = Field(default=None, alias="projectionHash")
    boundary_token: str | None = Field(default=None, alias="boundaryToken")
    source_range: AuctionLotsGridFillCommitRange = Field(alias="sourceRange")
    target_range: AuctionLotsGridFillCommitRange = Field(alias="targetRange")
    source_row_ids: list[str] = Field(default_factory=list, alias="sourceRowIds")
    target_row_ids: list[str] = Field(default_factory=list, alias="targetRowIds")
    fill_columns: list[str] = Field(default_factory=list, alias="fillColumns")
    reference_columns: list[str] = Field(default_factory=list, alias="referenceColumns")
    mode: Literal["copy"]
    projection: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] | None = None
    workspace_id: str | None = None
    table_id: str | None = None
    user_id: str | None = None
    session_id: str | None = None
