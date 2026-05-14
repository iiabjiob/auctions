from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class GridHistoryMutationRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    table_id: str = Field(alias="tableId", min_length=1)
    user_id: str | None = Field(default=None, alias="userId")
    session_id: str | None = Field(default=None, alias="sessionId")


class GridHistoryMutationResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    operation_id: str | None = Field(default=None, alias="operationId")
    action: str | None = None
    dataset_version: int = Field(alias="datasetVersion")
    revision: str | None = None
    updated_rows: list[Any] = Field(alias="updatedRows")
    rows: list[Any] = Field(default_factory=list)
    committed: list[dict[str, Any]] = Field(default_factory=list)
    committed_row_ids: list[str] = Field(default_factory=list, alias="committedRowIds")
    rejected: list[dict[str, Any]] = Field(default_factory=list)
    affected_rows: int = Field(default=0, alias="affectedRows")
    affected_cells: int = Field(default=0, alias="affectedCells")
    can_undo: bool | None = Field(default=None, alias="canUndo")
    can_redo: bool | None = Field(default=None, alias="canRedo")
    invalidation: dict[str, Any] | None = None
    latest_undo_operation_id: str | None = Field(default=None, alias="latestUndoOperationId")
    latest_redo_operation_id: str | None = Field(default=None, alias="latestRedoOperationId")


class GridHistoryStatusResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    can_undo: bool = Field(alias="canUndo")
    can_redo: bool = Field(alias="canRedo")
