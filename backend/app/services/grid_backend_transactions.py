from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession


async def prepare_session_for_package_transaction(session: AsyncSession) -> None:
    """Close an implicit read-only transaction before package-owned mutations."""
    in_transaction = getattr(session, "in_transaction", None)
    if callable(in_transaction) and in_transaction():
        await session.commit()
