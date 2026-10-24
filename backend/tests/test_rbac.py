"""Tier and authorization matrix tests."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.api.deps import (
    AdminUser,
    GroupCreatorUser,
    get_current_user,
    require_admin,
    require_group_creator,
)
from app.core.config import Settings
from app.core.database import get_session
from app.core.enums import UserTier
from app.core.security import create_access_token
from app.models.user import User
from tests.helpers import access_headers, make_user


@pytest.fixture()
def rbac_client(engine) -> Generator[TestClient, None, None]:
    app = FastAPI()

    @app.get("/creator")
    def creator(user: GroupCreatorUser):
        return {"id": user.id}

    @app.get("/admin")
    def admin(user: AdminUser):
        return {"id": user.id}

    @app.get("/authenticated")
    def authenticated(user: Annotated[User, Depends(get_current_user)]):
        return {"id": user.id}

    @app.get("/admin-dependency")
    def admin_dependency(_user: Annotated[User, Depends(require_admin)]):
        return {"ok": True}

    @app.get("/creator-dependency")
    def creator_dependency(_user: Annotated[User, Depends(require_group_creator)]):
        return {"ok": True}

    def override_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as client:
        yield client


TIER_MATRIX = [
    (None, 401),
    (UserTier.SYNC_USERS, 403),
    (UserTier.GROUP_CREATORS, 200),
    (UserTier.ADMIN, 200),
]


@pytest.mark.parametrize(("tier", "expected"), TIER_MATRIX)
def test_group_creator_matrix(rbac_client, session, tier, expected) -> None:
    headers = {}
    if tier is not None:
        user = make_user(session, tier=tier)
        headers = access_headers(user)
    response = rbac_client.get("/creator", headers=headers)
    assert response.status_code == expected


ADMIN_MATRIX = [
    (None, 401),
    (UserTier.SYNC_USERS, 403),
    (UserTier.GROUP_CREATORS, 403),
    (UserTier.ADMIN, 200),
]


@pytest.mark.parametrize(("tier", "expected"), ADMIN_MATRIX)
def test_admin_matrix(rbac_client, session, tier, expected) -> None:
    headers = {}
    if tier is not None:
        user = make_user(session, tier=tier)
        headers = access_headers(user)
    response = rbac_client.get("/admin", headers=headers)
    assert response.status_code == expected
    if expected == 403:
        assert response.json()["detail"]


def test_invalid_and_expired_tokens_are_rejected(rbac_client, session) -> None:
    assert (
        rbac_client.get(
            "/authenticated", headers={"Authorization": "Bearer nope.nope.nope"}
        ).status_code
        == 401
    )

    user = make_user(session)
    expired = create_access_token(
        user.id,
        secret=Settings(_env_file=None).jwt_secret,
        ttl_seconds=900,
        now=datetime.now(UTC) - timedelta(hours=2),
    )
    assert (
        rbac_client.get(
            "/authenticated", headers={"Authorization": f"Bearer {expired}"}
        ).status_code
        == 401
    )


def test_token_for_missing_user_is_rejected(rbac_client, session) -> None:
    user = make_user(session, email="delete-me@example.com")
    headers = access_headers(user)
    session.delete(user)
    session.commit()
    assert rbac_client.get("/authenticated", headers=headers).status_code == 401


def test_tier_change_takes_effect_on_next_request(client: TestClient, session) -> None:
    user = make_user(session, email="promote@example.com", tier=UserTier.SYNC_USERS)
    headers = access_headers(user)

    assert client.get("/api/admin/metrics", headers=headers).status_code == 403

    user.tier = UserTier.ADMIN.value
    session.add(user)
    session.commit()

    # The same access token now grants admin because tier is read from the DB.
    assert client.get("/api/admin/metrics", headers=headers).status_code == 200


def test_unknown_tier_never_grants_access(client: TestClient, session) -> None:
    user = make_user(session, email="unknown-tier@example.com")
    user.tier = "superuser"
    session.add(user)
    session.commit()
    headers = access_headers(user)

    assert client.get("/api/admin/metrics", headers=headers).status_code == 403
    assert client.get("/api/auth/me", headers=headers).json()["user"]["tier"] == "sync_users"


def test_missing_user_tier_is_not_accepted(client: TestClient) -> None:
    user = User(id="usr_missing", email="missing@example.com", tier=UserTier.ADMIN.value)
    headers = access_headers(user)
    assert client.get("/api/admin/metrics", headers=headers).status_code == 401
