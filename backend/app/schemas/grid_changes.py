from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


GridChangeType = Literal["row_updated", "row_inserted", "row_deleted", "invalidation"]


class GridChangeEntry(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: GridChangeType
    row_id: str | None = Field(default=None, alias="rowId")
    payload: dict[str, Any] = Field(default_factory=dict)


class GridChangeFeedResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    dataset_version: int = Field(alias="datasetVersion")
    changes: list[GridChangeEntry]
    has_more: bool = Field(alias="hasMore")
