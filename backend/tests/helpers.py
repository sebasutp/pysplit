"""Small helpers shared by Stage 4 test modules."""

from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import Settings, get_settings
from app.core.enums import UserTier
from app.core.ids import new_id
from app.core.security import create_access_token
from app.models.user import User


def make_user(
    session: Session,
    *,
    email: str | None = None,
    name: str = "Test User",
    tier: UserTier = UserTier.SYNC_USERS,
    image: str | None = None,
) -> User:
    user = User(
        id=new_id("usr"),
        email=email or f"user-{uuid4().hex}@example.com",
        name=name,
        image=image,
        tier=tier.value,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def access_headers(
    user: User,
    *,
    settings: Settings | None = None,
    ttl_seconds: int = 900,
) -> dict[str, str]:
    active = settings or get_settings()
    token = create_access_token(
        user.id,
        secret=active.jwt_secret,
        ttl_seconds=ttl_seconds,
    )
    return {"Authorization": f"Bearer {token}"}


def csrf_headers(
    client: TestClient,
    *,
    origin: str = "http://testserver",
) -> dict[str, str]:
    token = client.cookies.get("pysplit_csrf") or ""
    return {"Origin": origin, "X-CSRF-Token": token}


def mock_login(
    client: TestClient,
    *,
    email: str,
    name: str = "Test User",
    tier: UserTier | None = None,
    origin: str = "http://testserver",
):
    body: dict[str, str] = {"email": email, "name": name}
    if tier is not None:
        body["tier"] = tier.value
    return client.post(
        "/api/auth/mock-login",
        json=body,
        headers={"Origin": origin},
    )
