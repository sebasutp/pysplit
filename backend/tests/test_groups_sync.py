"""Stage 11 tests: two-device group membership and synchronized lists."""

from __future__ import annotations

from sqlmodel import Session, select

from app.models.expense import Expense
from app.models.user_group import UserGroup
from tests.helpers import access_headers, make_expense, make_group, make_user


def _operation(
    *,
    op_id: str,
    group_id: str,
    op_type: str,
    base_version: int | None = None,
    payload: dict,
) -> dict:
    return {
        "op_id": op_id,
        "group_id": group_id,
        "entity_type": "user_group",
        "entity_id": group_id,
        "op_type": op_type,
        "base_version": base_version,
        "payload": payload,
        "client_time": "2026-10-27T12:00:00Z",
    }


def _push(client, operations: list[dict], user):
    return client.post(
        "/api/sync/push",
        json={"operations": operations},
        headers=access_headers(user),
    )


def test_a_group_created_on_one_device_appears_on_the_second(client, session: Session):
    owner = make_user(session, email="owner@example.com", name="Owner")
    group, _ = make_group(session, name="Shared household")
    headers = access_headers(owner)

    # Device A claims the group through the sync push engine.
    claimed = _push(
        client,
        [
            _operation(
                op_id="op-claim-a",
                group_id=group.id,
                op_type="create",
                payload={},
            )
        ],
        owner,
    )
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["results"][0]["status"] == "applied"

    # Device B pulls the change feed rather than reading the same test's
    # in-memory rows, then sees the group in its complete account scope.
    pulled = client.post(
        "/api/sync/pull",
        json={"cursor": 0, "group_ids": [group.id], "limit": 500},
        headers=headers,
    )
    assert pulled.status_code == 200, pulled.text
    assert "user_group" in {
        change["entity_type"] for change in pulled.json()["changes"]
    }

    second = client.post("/api/groups/sync", json={}, headers=headers)
    assert second.status_code == 200, second.text
    assert [item["id"] for item in second.json()["groups"]] == [group.id]
    assert second.json()["is_authenticated"] is True


def test_star_and_archive_are_last_writer_wins_per_user(client, session: Session):
    user = make_user(session, email="sync@example.com")
    other = make_user(session, email="other@example.com")
    group, _ = make_group(session)

    claim = client.post(
        "/api/groups/sync",
        json={"local_group_ids": [group.id]},
        headers=access_headers(user),
    )
    assert claim.status_code == 200

    # Device A stars the group.
    starred = _push(
        client,
        [
            _operation(
                op_id="op-star-a",
                group_id=group.id,
                op_type="update",
                base_version=1,
                payload={"is_starred": True},
            )
        ],
        user,
    ).json()["results"][0]
    assert starred["status"] == "applied"
    assert starred["entity"]["is_starred"] is True

    # Device B archives it with a stale base version. Membership is LWW: the
    # write still applies and B becomes the latest value for this user only.
    archived = _push(
        client,
        [
            _operation(
                op_id="op-archive-b",
                group_id=group.id,
                op_type="update",
                base_version=999,
                payload={"is_archived": True, "is_starred": False},
            )
        ],
        user,
    ).json()["results"][0]
    assert archived["status"] == "applied"
    assert archived["entity"]["is_starred"] is False
    assert archived["entity"]["is_archived"] is True

    session.expire_all()
    membership = session.get(UserGroup, (user.id, group.id))
    assert membership is not None
    assert membership.is_starred is False
    assert membership.is_archived is True

    # The other user's membership is untouched.
    other_claim = client.post(
        "/api/groups/sync",
        json={"local_group_ids": [group.id]},
        headers=access_headers(other),
    )
    assert other_claim.status_code == 200
    other_view = other_claim.json()["groups"][0]
    assert other_view["is_starred"] is False
    assert other_view["is_archived"] is False


def test_star_and_archive_stay_mutually_exclusive_for_a_guest_claim(
    client, session: Session
):
    user = make_user(session, email="exclusive@example.com")
    group, _ = make_group(session)

    claim = client.post(
        "/api/groups/sync",
        json={"local_group_ids": [group.id], "starred_group_ids": [group.id]},
        headers=access_headers(user),
    )
    assert claim.status_code == 200
    session.expire_all()
    assert session.get(UserGroup, (user.id, group.id)).is_starred is True

    # Device B archives the group as a guest and then signs in. Its claim is a
    # positive-only archive signal; it must clear the star rather than leave
    # both flags set.
    archived = _push(
        client,
        [
            _operation(
                op_id="op-guest-archive",
                group_id=group.id,
                op_type="update",
                base_version=1,
                payload={"is_archived": True},
            )
        ],
        user,
    ).json()["results"][0]
    assert archived["status"] == "applied"
    assert archived["entity"]["is_starred"] is False
    assert archived["entity"]["is_archived"] is True

    session.expire_all()
    membership = session.get(UserGroup, (user.id, group.id))
    assert membership is not None
    assert (membership.is_starred, membership.is_archived) == (False, True)

    # The merge endpoint uses the same exclusion rule.
    restored = client.post(
        "/api/groups/sync",
        json={"local_group_ids": [group.id], "starred_group_ids": [group.id]},
        headers=access_headers(user),
    )
    assert restored.status_code == 200
    session.expire_all()
    membership = session.get(UserGroup, (user.id, group.id))
    assert (membership.is_starred, membership.is_archived) == (True, False)


def test_group_list_read_does_not_claim_a_removed_membership(
    client, session: Session
):
    user = make_user(session, email="list-read@example.com")
    group, _ = make_group(session)

    claim = client.post(
        "/api/groups/sync",
        json={"local_group_ids": [group.id]},
        headers=access_headers(user),
    )
    assert claim.status_code == 200
    assert client.delete(
        f"/api/groups/{group.id}/membership", headers=access_headers(user)
    ).status_code == 204

    # Another device still has the ID in its recent list; a plain read filter
    # must not turn that stale ID back into a membership.
    listed = client.post(
        "/api/groups/sync",
        json={"group_ids": [group.id]},
        headers=access_headers(user),
    )
    assert listed.status_code == 200
    assert listed.json()["groups"] == []
    session.expire_all()
    assert session.get(UserGroup, (user.id, group.id)) is None


def test_removing_membership_removes_the_list_entry_but_keeps_group_data(
    client, session: Session
):
    user = make_user(session, email="leave@example.com")
    group, people = make_group(session, name="Keep my data")
    expense = make_expense(
        session,
        group=group,
        paid_by=people["Alice"],
        paid_for=[(people["Alice"], 1), (people["Bob"], 1)],
        amount=4200,
        title="Groceries",
    )
    headers = access_headers(user)
    client.post(
        "/api/groups/sync",
        json={"local_group_ids": [group.id]},
        headers=headers,
    )

    removed = client.delete(f"/api/groups/{group.id}/membership", headers=headers)
    assert removed.status_code == 204

    # The group disappears from the synchronized list...
    listed = client.post("/api/groups/sync", json={}, headers=headers)
    assert listed.status_code == 200
    assert listed.json()["groups"] == []
    assert (
        session.exec(select(UserGroup).where(UserGroup.user_id == user.id)).all() == []
    )

    # ...but the capability URL and its financial data are still intact.
    detail = client.get(f"/api/groups/{group.id}")
    assert detail.status_code == 200
    assert detail.json()["name"] == "Keep my data"
    expenses = client.get(f"/api/groups/{group.id}/expenses")
    assert expenses.status_code == 200
    assert [item["id"] for item in expenses.json()["items"]] == [expense.id]
    session.expire_all()
    assert session.get(Expense, expense.id) is not None
