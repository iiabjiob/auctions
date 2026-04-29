from __future__ import annotations

from pydantic import BaseModel, Field


class AuthUserResponse(BaseModel):
    id: str
    email: str
    full_name: str


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class AuthSessionResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: AuthUserResponse


class AuthPublicConfigResponse(BaseModel):
    default_user_enabled: bool
    default_user_email: str | None = None
