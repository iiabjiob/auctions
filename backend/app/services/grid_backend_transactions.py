from __future__ import annotations

from collections.abc import Awaitable
from typing import TypeVar

from affino_grid_backend import ApiException
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auction import AuctionLotDetailCache, AuctionLotRecord, AuctionLotWorkItem
from app.models.procurement import ProcurementLotRecord


T = TypeVar("T")
GRID_MUTATION_LOCK_TIMEOUT_MS = 1_000
POSTGRES_LOCK_NOT_AVAILABLE_SQLSTATE = "55P03"


async def prepare_session_for_package_transaction(session: AsyncSession) -> None:
    """Close an implicit read-only transaction before package-owned mutations."""
    in_transaction = getattr(session, "in_transaction", None)
    if callable(in_transaction) and in_transaction():
        await session.commit()


async def run_package_grid_mutation(awaitable: Awaitable[T]) -> T:
    try:
        return await awaitable
    except DBAPIError as error:
        if is_grid_lock_timeout_error(error):
            raise ApiException(
                status_code=409,
                code="row-locked",
                message="Grid row is locked by another operation",
            ) from error
        raise


async def apply_grid_mutation_lock_timeout(session: AsyncSession) -> None:
    await session.execute(text(f"SET LOCAL lock_timeout = {GRID_MUTATION_LOCK_TIMEOUT_MS}"))


def is_grid_lock_timeout_error(error: DBAPIError) -> bool:
    original = getattr(error, "orig", None)
    sqlstate = getattr(original, "sqlstate", None) or getattr(original, "pgcode", None)
    return sqlstate == POSTGRES_LOCK_NOT_AVAILABLE_SQLSTATE


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
