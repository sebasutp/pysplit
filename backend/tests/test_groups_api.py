"""Stage 5A tests: groups, participants and capability URLs."""

from __future__ import annotations

from datetime import date

from sqlmodel import Session, select

from app.core.enums import UserTier
from app.models.activity import Activity
from app.models.group import Group
from app.models.participant import Participant
from app.models.user_group import UserGroup
from app.schemas.groups import GroupCreate, GroupUpdate
from app.services import groups as groups_service
from tests.helpers import access_headers, make_expense, make_group, make_user


def test_create_group(client, session: Session):
    creator = make_user(session, tier=UserTier.GROUP_CREATORS)
    response = client.post(
        "/api/groups",
        json={
            "name": "Lisbon",
            "information": "Summer trip",
            "currency": "€",
            "currency_code": "EUR",
            "participants": [{"id": "p1", "name": "Ada"}, {"name": "Grace"}],
        },
        headers=access_headers(creator),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "Lisbon"
    assert body["currency_code"] == "EUR"
    assert [participant["name"] for participant in body["participants"]] == ["Ada", "Grace"]
    assert body["participants"][0]["id"] == "p1"
    assert body["user_group"]["group_id"] == body["id"]
    assert body["version"] == 1

    stored = session.exec(select(Group).where(Group.id == body["id"])).one()
    assert stored.name == "Lisbon"


def test_create_group_requires_creator_tier(client, session: Session):
    sync_user = make_user(session, tier=UserTier.SYNC_USERS)
    payload = {"name": "Trip", "currency": "$", "participants": [{"name": "Ada"}]}
    assert client.post("/api/groups", json=payload).status_code == 401
    assert (
        client.post("/api/groups", json=payload, headers=access_headers(sync_user)).status_code
        == 403
    )


def test_create_group_rejects_duplicate_participant_names(client, session: Session):
    creator = make_user(session, tier=UserTier.GROUP_CREATORS)
    response = client.post(
        "/api/groups",
        json={
            "name": "Trip",
            "currency": "$",
            "participants": [{"name": "Ada"}, {"name": "Ada"}],
        },
        headers=access_headers(creator),
    )
    assert response.status_code == 422

    duplicate_ids = client.post(
        "/api/groups",
        json={
            "name": "Trip",
            "currency": "$",
            "participants": [
                {"id": "duplicate", "name": "Ada"},
                {"id": "duplicate", "name": "Grace"},
            ],
        },
        headers=access_headers(creator),
    )
    assert duplicate_ids.status_code == 422


def test_list_groups_by_ids_and_secure_default(client, session: Session):
    first, _ = make_group(session, name="Alpha")
    second, _ = make_group(session, name="Beta")
    assert client.get("/api/groups").json()["items"] == []

    response = client.get("/api/groups", params={"ids": f"{second.id},{first.id},missing"})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert [item["name"] for item in body["items"]] == ["Alpha", "Beta"]
    assert {item["name"] for item in body["items"]} == {"Alpha", "Beta"}


def test_list_groups_for_authenticated_user(client, session: Session):
    user = make_user(session)
    first, _ = make_group(session, name="First")
    second, _ = make_group(session, name="Second")
    session.add(UserGroup(user_id=user.id, group_id=first.id, is_starred=True))
    session.add(UserGroup(user_id=user.id, group_id=second.id, is_archived=True))
    session.commit()

    headers = access_headers(user)
    response = client.get("/api/groups", headers=headers)
    assert response.status_code == 200
    assert response.json()["total"] == 2

    starred = client.get("/api/groups", params={"status": "starred"}, headers=headers).json()
    assert [item["id"] for item in starred["items"]] == [first.id]
    archived = client.get("/api/groups", params={"status": "archived"}, headers=headers).json()
    assert [item["id"] for item in archived["items"]] == [second.id]
    assert starred["items"][0]["user_group"]["is_starred"] is True


def test_get_group_and_missing_group(client, session: Session):
    group, participants = make_group(session, name="Readable")
    response = client.get(f"/api/groups/{group.id}")
    assert response.status_code == 200
    assert response.json()["name"] == "Readable"
    assert {item["name"] for item in response.json()["participants"]} == set(participants)
    assert client.get("/api/groups/does-not-exist").status_code == 404


def test_group_details_lists_participants_with_expenses(client, session: Session):
    group, people = make_group(session)
    make_expense(
        session,
        group=group,
        paid_by=people["Alice"],
        paid_for=[(people["Alice"], 1), (people["Bob"], 1)],
        amount=1000,
        expense_date=date(2026, 2, 1),
    )
    response = client.get(f"/api/groups/{group.id}/details")
    assert response.status_code == 200
    body = response.json()
    assert body["group"]["id"] == group.id
    assert set(body["participants_with_expenses"]) == {people["Alice"].id, people["Bob"].id}
    assert body["participantsWithExpenses"] == body["participants_with_expenses"]
    assert {item["name"] for item in body["participants_with_expense_details"]} == {
        "Alice",
        "Bob",
    }


def test_update_group_replaces_participants_and_logs_activity(client, session: Session):
    group, people = make_group(session, participants=("Alice", "Bob", "Carol"))
    response = client.patch(
        f"/api/groups/{group.id}",
        json={
            "name": "Renamed",
            "information": "Updated",
            "participants": [
                {"id": people["Alice"].id, "name": "Alicia"},
                {"id": people["Carol"].id, "name": "Carol"},
                {"name": "Dave"},
            ],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "Renamed"
    assert body["version"] == 2
    assert {participant["name"] for participant in body["participants"]} == {
        "Alicia",
        "Carol",
        "Dave",
    }

    activity = session.exec(select(Activity).where(Activity.group_id == group.id)).one()
    assert activity.activity_type == "UPDATE_GROUP"


def test_group_update_partial_preserves_participants(client, session: Session):
    group, people = make_group(session)
    response = client.patch(f"/api/groups/{group.id}", json={"information": "Only info"})
    assert response.status_code == 200
    assert response.json()["information"] == "Only info"
    assert {p["id"] for p in response.json()["participants"]} == {
        people["Alice"].id,
        people["Bob"].id,
    }


def test_group_update_unknown_participant_id_creates_or_rejects(client, session: Session):
    group, _ = make_group(session)
    own_new = client.patch(
        f"/api/groups/{group.id}",
        json={"participants": [{"id": "client-par", "name": "Client"}]},
    )
    assert own_new.status_code == 200
    assert own_new.json()["participants"][0]["id"] == "client-par"

    other, _ = make_group(session)
    response = client.patch(
        f"/api/groups/{other.id}",
        json={"participants": [{"id": "client-par", "name": "Stolen"}]},
    )
    assert response.status_code == 422


def test_participant_crud(client, session: Session):
    group, _ = make_group(session, participants=("Alice",))
    created = client.post(
        f"/api/groups/{group.id}/participants",
        json={"name": "Bob"},
    )
    assert created.status_code == 201
    participant_id = created.json()["id"]

    duplicate = client.post(f"/api/groups/{group.id}/participants", json={"name": "Bob"})
    assert duplicate.status_code == 422

    listed = client.get(f"/api/groups/{group.id}/participants")
    assert listed.status_code == 200
    assert {row["name"] for row in listed.json()} == {"Alice", "Bob"}

    renamed = client.patch(
        f"/api/groups/{group.id}/participants/{participant_id}",
        json={"name": "Robert"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Robert"
    assert renamed.json()["version"] == 2

    deleted = client.delete(f"/api/groups/{group.id}/participants/{participant_id}")
    assert deleted.status_code == 204
    assert {row["name"] for row in client.get(f"/api/groups/{group.id}/participants").json()} == {
        "Alice"
    }
    assert client.get(f"/api/groups/{group.id}/participants").status_code == 200


def test_participant_endpoints_validate_group(client, session: Session):
    group, _ = make_group(session)
    other, _ = make_group(session)
    participant = session.exec(select(Participant).where(Participant.group_id == other.id)).first()
    assert participant is not None
    response = client.patch(
        f"/api/groups/{group.id}/participants/{participant.id}",
        json={"name": "Nope"},
    )
    assert response.status_code == 404
    assert client.delete(f"/api/groups/{group.id}/participants/missing").status_code == 404


def test_service_create_and_update_are_idempotent(session: Session):
    payload = GroupCreate(
        id="fixed-group",
        name="Fixed",
        currency="$",
        participants=[{"name": "Ada"}],
    )
    first = groups_service.create_group(session, payload)
    second = groups_service.create_group(session, payload)
    assert first.id == second.id == "fixed-group"
    assert len(second.participants) == 1

    updated = groups_service.update_group(
        session,
        "fixed-group",
        GroupUpdate(name="New name"),
    )
    assert updated.name == "New name"
