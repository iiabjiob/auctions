from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password, verify_password
from app.models import UserModel


class AuthService:
    async def ensure_default_user(self, session: AsyncSession) -> UserModel | None:
        settings = get_settings()
        if not settings.default_user_enabled:
            return None

        resolved_password = self._resolve_default_user_password(settings.default_user_password)
        if resolved_password is None:
            return None

        normalized_email = settings.default_user_email.strip().lower()
        user = await session.scalar(select(UserModel).where(UserModel.email == normalized_email))
        now = datetime.now(UTC)
        password_hash = hash_password(resolved_password)

        if user is None:
            user = UserModel(
                id=f"user_{uuid4().hex[:8]}",
                email=normalized_email,
                full_name=settings.default_user_name.strip() or "Default User",
                password_hash=password_hash,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

        updates_required = False
        if user.full_name != settings.default_user_name:
            user.full_name = settings.default_user_name
            updates_required = True
        if not verify_password(resolved_password, user.password_hash):
            user.password_hash = password_hash
            updates_required = True
        if not user.is_active:
            user.is_active = True
            updates_required = True

        if updates_required:
            user.updated_at = now
            await session.commit()
            await session.refresh(user)

        return user

    async def login(
        self,
        session: AsyncSession,
        *,
        email: str,
        password: str,
    ) -> dict[str, object]:
        normalized_email = email.strip().lower()
        user = await session.scalar(select(UserModel).where(UserModel.email == normalized_email))
        if user is None or not verify_password(password, user.password_hash):
            raise self._authentication_error()
        if not user.is_active:
            raise self._authentication_error()

        user.updated_at = datetime.now(UTC)
        await session.commit()
        return {
            "access_token": create_access_token(user.id),
            "token_type": "bearer",
            "user": self.serialize_user(user),
        }

    def serialize_user(self, user: UserModel) -> dict[str, object]:
        return {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
        }

    def _authentication_error(self) -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    def _resolve_default_user_password(self, password: str | None) -> str | None:
        if password is None:
            return None
        normalized = password.strip()
        return normalized or None


auth_service = AuthService()
