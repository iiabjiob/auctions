from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.auction_grid import AuctionLotsGridPullRow


class GridHistoryMutationRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    table_id: str = Field(alias="tableId", min_length=1)
    user_id: str | None = Field(default=None, alias="userId")
    session_id: str | None = Field(default=None, alias="sessionId")


class GridHistoryMutationResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    dataset_version: int = Field(alias="datasetVersion")
    updated_rows: list[AuctionLotsGridPullRow] = Field(alias="updatedRows")


class GridHistoryStatusResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    can_undo: bool = Field(alias="canUndo")
    can_redo: bool = Field(alias="canRedo")
