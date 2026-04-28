from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.infrastructure.db.database import get_db
from app.models import UserModel

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_db),
) -> UserModel:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _authentication_error()

    try:
        payload = decode_access_token(credentials.credentials)
    except ValueError as exc:
        raise _authentication_error() from exc

    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject:
        raise _authentication_error()

    user = await session.scalar(select(UserModel).where(UserModel.id == subject))
    if user is None or not user.is_active:
        raise _authentication_error()

    return user


def _authentication_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication is required.",
        headers={"WWW-Authenticate": "Bearer"},
    )
