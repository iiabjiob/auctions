from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auction import AuctionLotDetailCache, AuctionLotRecord, AuctionLotWorkItem
from app.models.procurement import ProcurementLotRecord


T = TypeVar("T")
GRID_PACKAGE_MUTATION_TIMEOUT_SECONDS = 30.0


async def prepare_session_for_package_transaction(session: AsyncSession) -> None:
    """Close an implicit read-only transaction before package-owned mutations."""
    in_transaction = getattr(session, "in_transaction", None)
    if callable(in_transaction) and in_transaction():
        await session.commit()


async def run_package_grid_mutation(awaitable: Awaitable[T]) -> T:
    async with asyncio.timeout(GRID_PACKAGE_MUTATION_TIMEOUT_SECONDS):
        return await awaitable


async def refresh_package_grid_row(session: AsyncSession, row: object) -> None:
    refresh = getattr(session, "refresh", None)
    if not callable(refresh):
        return
    if hasattr(row, "record") and isinstance(row.record, AuctionLotRecord):
        await refresh(row.record)
        work_item = getattr(row, "work_item", None)
        detail_cache = getattr(row, "detail_cache", None)
        if isinstance(work_item, AuctionLotWorkItem):
            await refresh(work_item)
        if isinstance(detail_cache, AuctionLotDetailCache):
            await refresh(detail_cache)
        return
    if isinstance(row, ProcurementLotRecord):
        await refresh(row)
