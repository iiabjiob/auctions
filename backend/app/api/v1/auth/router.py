from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.infrastructure.db.database import get_db
from app.models import UserModel
from app.schemas.auth import AuthPublicConfigResponse, AuthSessionResponse, AuthUserResponse, LoginRequest
from app.services.auth import auth_service

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])


@router.post("/login", response_model=AuthSessionResponse)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> AuthSessionResponse:
    await auth_service.ensure_default_user(db)
    return AuthSessionResponse.model_validate(
        await auth_service.login(db, email=payload.email, password=payload.password)
    )


@router.get("/public-config", response_model=AuthPublicConfigResponse)
async def public_config() -> AuthPublicConfigResponse:
    settings = get_settings()
    demo_user_available = settings.default_user_enabled and bool((settings.default_user_password or "").strip())
    return AuthPublicConfigResponse(
        default_user_enabled=demo_user_available,
        default_user_email=settings.default_user_email if demo_user_available else None,
    )


@router.get("/me", response_model=AuthUserResponse)
async def current_user_profile(current_user: UserModel = Depends(get_current_user)) -> AuthUserResponse:
    return AuthUserResponse.model_validate(auth_service.serialize_user(current_user))
