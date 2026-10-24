"""Shared FastAPI dependencies.

Routers depend on these aliases instead of importing models or the engine.
Authentication reads the tier from the database on every request, so an admin
promotion or demotion takes effect immediately even while an access token is
still valid.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlmodel import Session

from app.core.config import Settings, get_settings
from app.core.database import get_session
from app.core.enums import UserTier, normalize_user_tier
from app.core.security import TokenError, verify_access_token
from app.models.user import User
from app.services.auth import find_user_by_id

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

_UNAUTHENTICATED = "You must be signed in to perform this action."
_FORBIDDEN_CREATOR = (
    "Group creation requires administrator approval. Your account is currently in "
    "the sync users tier."
)
_FORBIDDEN_ADMIN = "This action is restricted to administrators."


def bearer_token(request: Request) -> str | None:
    """Extract a bearer token without raising for anonymous requests."""
    header = request.headers.get("authorization")
    if not header:
        return None
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return None
    return value.strip()


def get_optional_user(
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
) -> User | None:
    """Return the authenticated user, or ``None`` for missing/invalid tokens."""
    token = bearer_token(request)
    if token is None:
        return None
    try:
        claims = verify_access_token(token, secret=settings.jwt_secret)
    except TokenError:
        return None
    return find_user_by_id(session, claims.subject)


def get_current_user(
    user: Annotated[User | None, Depends(get_optional_user)],
) -> User:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_UNAUTHENTICATED,
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_group_creator(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    if normalize_user_tier(user.tier) not in {
        UserTier.GROUP_CREATORS,
        UserTier.ADMIN,
    }:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_FORBIDDEN_CREATOR,
        )
    return user


def require_admin(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    if normalize_user_tier(user.tier) != UserTier.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_FORBIDDEN_ADMIN,
        )
    return user


OptionalUser = Annotated[User | None, Depends(get_optional_user)]
CurrentUser = Annotated[User, Depends(get_current_user)]
GroupCreatorUser = Annotated[User, Depends(require_group_creator)]
AdminUser = Annotated[User, Depends(require_admin)]
