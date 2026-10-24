"""Stage 4 admin API and bootstrap tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel, select

from app.core.enums import UserTier
from app.core.ids import new_id
from app.models.account import Account
from app.models.category import Category
from app.models.expense import Expense
from app.models.group import Group
from app.models.participant import Participant
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.models.user_group import UserGroup
from app.scripts.make_admin import main as make_admin_main
from app.scripts.make_admin import make_admin
from tests.helpers import access_headers, make_user


def _admin_headers(session) -> dict[str, str]:
    admin = make_user(session, email="admin@example.com", tier=UserTier.ADMIN)
    return access_headers(admin)


def _group(session, name: str = "Trip") -> Group:
    group = Group(id=new_id("grp"), name=name, currency="$", currency_code="USD")
    session.add(group)
    session.commit()
    session.refresh(group)
    return group


def _participant(session, group: Group, name: str = "Alice") -> Participant:
    participant = Participant(id=new_id("par"), group_id=group.id, name=name)
    session.add(participant)
    session.commit()
    session.refresh(participant)
    return participant


def _expense(session, group: Group, participant: Participant, amount: int = 1000) -> Expense:
    category = Category(grouping="General", name="General")
    session.add(category)
    session.commit()
    session.refresh(category)
    expense = Expense(
        id=new_id("exp"),
        group_id=group.id,
        expense_date=datetime.now(UTC),
        title="Dinner",
        category_id=category.id or 0,
        amount=amount,
        paid_by_id=participant.id,
    )
    session.add(expense)
    session.commit()
    session.refresh(expense)
    return expense


# ---------------------------------------------------------------------------
# Metrics and users
# ---------------------------------------------------------------------------


def test_metrics(client: TestClient, session) -> None:
    headers = _admin_headers(session)
    make_user(session, email="sync@example.com", tier=UserTier.SYNC_USERS)
    make_user(session, email="creator@example.com", tier=UserTier.GROUP_CREATORS)
    group = _group(session)
    participant = _participant(session, group)
    _expense(session, group, participant)

    response = client.get("/api/admin/metrics", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_groups"] == 1
    assert payload["total_expenses"] == 1
    assert payload["total_users"] == 3
    assert payload["tier_counts"] == {
        "sync_users": 1,
        "group_creators": 1,
        "admin": 1,
    }


def test_list_users(client: TestClient, session) -> None:
    headers = _admin_headers(session)
    alice = make_user(
        session, email="alice@example.com", name="Alice", tier=UserTier.GROUP_CREATORS
    )
    bob = make_user(session, email="bob@example.com", name="Bob", tier=UserTier.SYNC_USERS)
    assert bob.email == "bob@example.com"
    group = _group(session)
    session.add(UserGroup(user_id=alice.id, group_id=group.id, is_starred=True))
    session.add(
        Account(
            id=new_id("acc"),
            user_id=alice.id,
            type="oauth",
            provider="github",
            provider_account_id="gh-1",
        )
    )
    session.commit()

    response = client.get("/api/admin/users", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    assert payload["limit"] == 10
    assert payload["offset"] == 0
    by_email = {item["email"]: item for item in payload["items"]}
    assert by_email["alice@example.com"]["providers"] == ["github"]
    assert by_email["alice@example.com"]["groups_count"] == 1
    assert by_email["alice@example.com"]["tier"] == "group_creators"
    assert by_email["bob@example.com"]["providers"] == []

    filtered = client.get("/api/admin/users?q=ali", headers=headers).json()
    assert filtered["total"] == 1
    assert filtered["items"][0]["email"] == "alice@example.com"

    tiered = client.get("/api/admin/users?tier=sync_users", headers=headers).json()
    assert tiered["total"] == 1
    assert tiered["items"][0]["email"] == "bob@example.com"

    paged = client.get("/api/admin/users?limit=1&offset=1", headers=headers).json()
    assert paged["total"] == 3
    assert len(paged["items"]) == 1

    assert client.get("/api/admin/users?limit=0", headers=headers).status_code == 422
    assert client.get("/api/admin/users?limit=101", headers=headers).status_code == 422


def test_preauthorize_user(client: TestClient, session) -> None:
    headers = _admin_headers(session)

    response = client.post(
        "/api/admin/users/preauthorize",
        headers=headers,
        json={"email": " New.User@Example.com ", "name": "New User"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["is_new"] is True
    assert payload["user"]["email"] == "new.user@example.com"
    assert payload["user"]["tier"] == "group_creators"
    assert payload["user"]["name"] == "New User"

    user = session.exec(select(User).where(User.email == "new.user@example.com")).one()

    updated = client.post(
        "/api/admin/users/preauthorize",
        headers=headers,
        json={"email": "new.user@example.com", "tier": "admin"},
    )
    assert updated.status_code == 200
    assert updated.json()["is_new"] is False
    assert updated.json()["user"]["tier"] == "admin"
    assert updated.json()["user"]["name"] == "New User"
    session.refresh(user)
    assert user.tier == "admin"

    invalid = client.post(
        "/api/admin/users/preauthorize",
        headers=headers,
        json={"email": "not-an-email"},
    )
    assert invalid.status_code == 422


def test_update_tier(client: TestClient, session) -> None:
    headers = _admin_headers(session)
    user = make_user(session, email="target@example.com", tier=UserTier.SYNC_USERS)

    response = client.patch(
        f"/api/admin/users/{user.id}/tier",
        headers=headers,
        json={"tier": "group_creators"},
    )
    assert response.status_code == 200
    assert response.json() == {"id": user.id, "tier": "group_creators"}

    session.refresh(user)
    assert user.tier == "group_creators"
    assert user.version == 2

    missing = client.patch(
        "/api/admin/users/does-not-exist/tier",
        headers=headers,
        json={"tier": "admin"},
    )
    assert missing.status_code == 404

    invalid = client.patch(
        f"/api/admin/users/{user.id}/tier",
        headers=headers,
        json={"tier": "owner"},
    )
    assert invalid.status_code == 422


def test_delete_user(client: TestClient, session) -> None:
    headers = _admin_headers(session)
    user = make_user(session, email="delete@example.com")
    group = _group(session)
    session.add(UserGroup(user_id=user.id, group_id=group.id))
    session.add(
        Account(
            id=new_id("acc"),
            user_id=user.id,
            type="oauth",
            provider="google",
            provider_account_id="g-1",
        )
    )
    session.add(
        RefreshToken(
            id=new_id("rt"),
            user_id=user.id,
            token_hash="hash-delete",
            expires_at=datetime.now(UTC),
        )
    )
    session.commit()

    response = client.delete(f"/api/admin/users/{user.id}", headers=headers)
    assert response.status_code == 204
    assert response.content == b""
    user_id = user.id
    session.expunge_all()
    assert session.get(User, user_id) is None
    assert session.exec(select(Account).where(Account.user_id == user_id)).all() == []
    assert session.exec(select(UserGroup).where(UserGroup.user_id == user_id)).all() == []
    assert session.exec(select(RefreshToken).where(RefreshToken.user_id == user_id)).all() == []

    assert client.delete(f"/api/admin/users/{user_id}", headers=headers).status_code == 404


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------


def test_list_groups(client: TestClient, session) -> None:
    headers = _admin_headers(session)
    trip = _group(session, "Trip")
    participant = _participant(session, trip)
    _expense(session, trip, participant)
    _group(session, "Flat")
    user = make_user(session, email="member@example.com")
    session.add(UserGroup(user_id=user.id, group_id=trip.id))
    session.commit()

    response = client.get("/api/admin/groups", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    by_name = {item["name"]: item for item in payload["items"]}
    assert by_name["Trip"]["participants_count"] == 1
    assert by_name["Trip"]["expenses_count"] == 1
    assert by_name["Trip"]["synced_users_count"] == 1
    assert by_name["Flat"]["expenses_count"] == 0

    searched = client.get("/api/admin/groups?q=Tri", headers=headers).json()
    assert searched["total"] == 1
    assert searched["items"][0]["id"] == trip.id

    by_id = client.get(f"/api/admin/groups?q={trip.id}", headers=headers).json()
    assert by_id["total"] == 1


def test_delete_group(client: TestClient, session) -> None:
    headers = _admin_headers(session)
    group = _group(session, "Delete Me")
    participant = _participant(session, group)
    expense = _expense(session, group, participant)
    user = make_user(session, email="member2@example.com")
    session.add(UserGroup(user_id=user.id, group_id=group.id))
    session.commit()

    group_id = group.id
    participant_id = participant.id
    expense_id = expense.id
    user_id = user.id

    response = client.delete(f"/api/admin/groups/{group_id}", headers=headers)
    assert response.status_code == 204
    session.expunge_all()
    assert session.get(Group, group_id) is None
    assert session.get(Participant, participant_id) is None
    assert session.get(Expense, expense_id) is None
    assert session.exec(select(UserGroup).where(UserGroup.group_id == group_id)).all() == []
    assert session.get(User, user_id) is not None

    assert client.delete(f"/api/admin/groups/{group_id}", headers=headers).status_code == 404


# ---------------------------------------------------------------------------
# Admin authorization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tier", "expected"),
    [
        (None, 401),
        (UserTier.SYNC_USERS, 403),
        (UserTier.GROUP_CREATORS, 403),
        (UserTier.ADMIN, 200),
    ],
)
def test_admin_endpoints_require_admin(client: TestClient, session, tier, expected) -> None:
    headers = {}
    if tier is not None:
        user = make_user(session, email=f"{tier.value}@example.com", tier=tier)
        headers = access_headers(user)
    response = client.get("/api/admin/metrics", headers=headers)
    assert response.status_code == expected


# ---------------------------------------------------------------------------
# Bootstrap CLI
# ---------------------------------------------------------------------------


def _file_database(tmp_path: Path) -> tuple[str, object]:
    path = tmp_path / "bootstrap.db"
    engine = create_engine(f"sqlite:///{path}")
    SQLModel.metadata.create_all(engine)
    return str(path), engine


def test_admin_bootstrap_creates_then_promotes(tmp_path: Path) -> None:
    path, engine = _file_database(tmp_path)

    created = make_admin(email="Owner@Example.com", db=path)
    assert created.is_new is True
    assert created.user.email == "owner@example.com"
    assert created.user.tier == UserTier.ADMIN

    again = make_admin(email="owner@example.com", db=path)
    assert again.is_new is False
    assert again.user.tier == UserTier.ADMIN

    with Session(engine) as session:
        user = session.exec(select(User)).one()
        assert user.tier == "admin"
    engine.dispose()


def test_admin_bootstrap_promotes_existing_user(tmp_path: Path) -> None:
    path, engine = _file_database(tmp_path)
    with Session(engine) as session:
        user = User(
            id=new_id("usr"),
            email="existing@example.com",
            name="Existing",
            tier=UserTier.SYNC_USERS.value,
        )
        session.add(user)
        session.commit()

    result = make_admin(email="existing@example.com", db=path)
    assert result.is_new is False
    assert result.user.tier == UserTier.ADMIN

    with Session(engine) as session:
        user = session.exec(select(User)).one()
        assert user.tier == "admin"
    engine.dispose()


def test_admin_bootstrap_cli(tmp_path: Path, capsys) -> None:
    path, engine = _file_database(tmp_path)
    assert make_admin_main(["--email", "cli@example.com", "--db", path]) == 0
    output = capsys.readouterr().out
    assert "cli@example.com" in output
    assert "admin" in output
    engine.dispose()


def test_admin_bootstrap_cli_reports_missing_schema(tmp_path: Path, capsys) -> None:
    empty = tmp_path / "empty.db"
    assert make_admin_main(["--email", "x@example.com", "--db", str(empty)]) == 2
    assert "could not update the database" in capsys.readouterr().err
