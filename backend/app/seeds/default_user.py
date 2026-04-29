from __future__ import annotations

import asyncio

from app.core.config import get_settings
from app.infrastructure.db.database import AsyncSessionLocal
from app.services.auth import auth_service


async def seed_default_user() -> None:
    settings = get_settings()
    async with AsyncSessionLocal() as session:
        user = await auth_service.ensure_default_user(session)

    if user is None:
        print("Default user seed skipped: default user is disabled or password is empty.")
        return

    print(f"Default user ensured: {settings.default_user_email.strip().lower()}")


def main() -> None:
    asyncio.run(seed_default_user())


if __name__ == "__main__":
    main()