"""Authentication request and response schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.core.enums import UserTier


class UserRead(BaseModel):
    id: str
    name: str | None = None
    email: str | None = None
    image: str | None = None
    tier: UserTier


class AuthProviders(BaseModel):
    google: bool = False
    github: bool = False


class MeResponse(BaseModel):
    user: UserRead | None = None
    providers: AuthProviders = Field(default_factory=AuthProviders)
    # Exposed so a SPA on another origin can echo it in ``X-CSRF-Token``.
    csrf_token: str | None = None


class RefreshResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: UserRead
    csrf_token: str


class MockLoginRequest(BaseModel):
    email: str | None = Field(default=None, max_length=320)
    name: str | None = Field(default=None, max_length=200)
    tier: UserTier | None = None


class MockLoginResponse(BaseModel):
    success: bool = True
    user: UserRead
    csrf_token: str | None = None
