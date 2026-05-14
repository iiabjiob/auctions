from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncSession


T = TypeVar("T")
GRID_PACKAGE_MUTATION_TIMEOUT_SECONDS = 30.0


async def prepare_session_for_package_transaction(session: AsyncSession) -> None:
    """Close an implicit read-only transaction before package-owned mutations."""
    in_transaction = getattr(session, "in_transaction", None)
    if callable(in_transaction) and in_transaction():
        await session.commit()


async def run_package_grid_mutation(awaitable: Awaitable[T]) -> T:
    return await asyncio.wait_for(awaitable, timeout=GRID_PACKAGE_MUTATION_TIMEOUT_SECONDS)
