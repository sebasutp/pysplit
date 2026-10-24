"""Stage 5A tests: authenticated group synchronization and membership."""

from __future__ import annotations

from sqlmodel import Session, select

from app.models.user_group import UserGroup
from tests.helpers import access_headers, make_group, make_user


def _membership(session: Session, user_id: str, group_id: str) -> UserGroup | None:
    return session.get(UserGroup, (user_id, group_id))


def test_merge_local_groups(client, session: Session):
    user = make_user(session)
    first, _ = make_group(session, name="First")
    second, _ = make_group(session, name="Second")
    headers = access_headers(user)

    response = client.post(
        "/api/groups/sync",
        json={
            "local_group_ids": [first.id, second.id, "missing"],
            "starred_group_ids": [first.id],
            "archived_group_ids": [second.id],
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["is_authenticated"] is True
    assert {item["id"] for item in body["groups"]} == {first.id, second.id}
    assert len(body["user_groups"]) == 2

    first_membership = _membership(session, user.id, first.id)
    second_membership = _membership(session, user.id, second.id)
    assert first_membership is not None and first_membership.is_starred is True
    assert second_membership is not None and second_membership.is_archived is True

    # Replaying the same merge does not duplicate rows.
    replay = client.post(
        "/api/groups/sync",
        json={
            "localGroupIds": [first.id, second.id],
            "starredGroupIds": [first.id],
        },
        headers=headers,
    )
    assert replay.status_code == 200
    rows = session.exec(select(UserGroup).where(UserGroup.user_id == user.id)).all()
    assert len(rows) == 2
    session.expire_all()
    assert _membership(session, user.id, first.id).is_starred is True
    assert _membership(session, user.id, second.id).is_archived is True


def test_sync_router_guest_and_authenticated(client, session: Session):
    group, _ = make_group(session, name="Guest Group")
    guest = client.post(
        "/api/groups/sync",
        json={"local_group_ids": [group.id], "starred_group_ids": [group.id]},
    )
    assert guest.status_code == 200
    guest_body = guest.json()
    assert guest_body["is_authenticated"] is False
    assert guest_body["isAuthenticated"] is False
    assert guest_body["groups"][0]["id"] == group.id
    assert guest_body["groups"][0]["is_starred"] is True
    assert guest_body["groups"][0]["isStarred"] is True
    assert guest_body["user_groups"] == []

    user = make_user(session)
    auth = client.post(
        "/api/groups/sync",
        json={"local_group_ids": [group.id]},
        headers=access_headers(user),
    )
    assert auth.status_code == 200
    assert auth.json()["is_authenticated"] is True
    assert auth.json()["groups"][0]["name"] == "Guest Group"


def test_record_access(client, session: Session):
    user = make_user(session)
    group, _ = make_group(session)
    response = client.post(f"/api/groups/{group.id}/access", headers=access_headers(user))
    assert response.status_code == 204
    assert _membership(session, user.id, group.id) is not None

    # Revisiting is idempotent.
    assert (
        client.post(f"/api/groups/{group.id}/access", headers=access_headers(user)).status_code
        == 204
    )
    rows = session.exec(select(UserGroup).where(UserGroup.user_id == user.id)).all()
    assert len(rows) == 1

    # Anonymous access and unknown groups are no-ops preserving capability URLs.
    assert client.post(f"/api/groups/{group.id}/access").status_code == 204
    assert (
        client.post("/api/groups/missing/access", headers=access_headers(user)).status_code == 204
    )
    assert len(session.exec(select(UserGroup)).all()) == 1


def test_toggle_star(client, session: Session):
    user = make_user(session)
    group, _ = make_group(session)
    headers = access_headers(user)
    response = client.patch(
        f"/api/groups/{group.id}/membership",
        json={"is_starred": True},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["is_starred"] is True
    assert response.json()["is_archived"] is False

    unstar = client.patch(
        f"/api/groups/{group.id}/membership",
        json={"is_starred": False},
        headers=headers,
    )
    assert unstar.status_code == 200
    assert unstar.json()["is_starred"] is False

    assert (
        client.patch(f"/api/groups/{group.id}/membership", json={"is_starred": True}).status_code
        == 401
    )


def test_toggle_archive(client, session: Session):
    user = make_user(session)
    group, _ = make_group(session)
    response = client.patch(
        f"/api/groups/{group.id}/membership",
        json={"is_archived": True},
        headers=access_headers(user),
    )
    assert response.status_code == 200
    assert response.json()["is_archived"] is True

    missing = client.patch(
        "/api/groups/missing/membership",
        json={"is_archived": True},
        headers=access_headers(user),
    )
    assert missing.status_code == 404


def test_remove_membership(client, session: Session):
    user = make_user(session)
    group, _ = make_group(session)
    headers = access_headers(user)
    client.post("/api/groups/sync", json={"local_group_ids": [group.id]}, headers=headers)
    assert _membership(session, user.id, group.id) is not None

    response = client.delete(f"/api/groups/{group.id}/membership", headers=headers)
    assert response.status_code == 204
    session.expire_all()
    assert _membership(session, user.id, group.id) is None

    # Removing again (or as a guest) is idempotent.
    assert client.delete(f"/api/groups/{group.id}/membership", headers=headers).status_code == 204
    assert client.delete(f"/api/groups/{group.id}/membership").status_code == 204
