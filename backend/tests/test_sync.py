"""Stage 6 tests: push/pull/bootstrap, idempotency and tombstones."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlmodel import Session, select

from app.core.enums import UserTier
from app.models.activity import Activity
from app.models.expense import Expense
from app.models.group import Group
from app.models.participant import Participant
from app.models.receipt import Receipt
from app.models.receipt_item import ReceiptItem
from app.models.receipt_item_portion import ReceiptItemPortion
from app.models.receipt_opt_out import ReceiptOptOut
from app.models.recurring_expense_link import RecurringExpenseLink
from app.models.sync_change import SyncChange
from app.models.user_group import UserGroup
from app.services import expenses as expenses_service
from app.services import sync as sync_service
from tests.helpers import access_headers, make_expense, make_group, make_user


def expense_payload(people: dict[str, Participant], **overrides) -> dict:
    payload = {
        "expense_date": "2026-02-01",
        "title": "Dinner",
        "category_id": 0,
        "amount": 1000,
        "paid_by_id": people["Alice"].id,
        "split_mode": "EVENLY",
        "paid_for": [
            {"participant_id": people["Alice"].id, "shares": 1},
            {"participant_id": people["Bob"].id, "shares": 1},
        ],
    }
    payload.update(overrides)
    return payload


def operation(
    *,
    op_id: str,
    group_id: str,
    entity_type: str,
    entity_id: str,
    op_type: str = "create",
    base_version: int | None = None,
    payload: dict | None = None,
) -> dict:
    return {
        "op_id": op_id,
        "group_id": group_id,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "op_type": op_type,
        "base_version": base_version,
        "payload": payload or {},
        "client_time": "2026-10-24T12:00:00Z",
    }


def push(client, operations: list[dict], **kwargs):
    return client.post("/api/sync/push", json={"operations": operations}, **kwargs)


def pull(client, cursor: int, group_ids: list[str], limit: int = 500, **kwargs):
    return client.post(
        "/api/sync/pull",
        json={"cursor": cursor, "group_ids": group_ids, "limit": limit},
        **kwargs,
    )


def test_push_create_pull_and_bootstrap(client, session: Session):
    group, people = make_group(session)
    response = push(
        client,
        [
            operation(
                op_id="op-create-1",
                group_id=group.id,
                entity_type="expense",
                entity_id="exp-client-1",
                payload=expense_payload(people),
            )
        ],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    result = body["results"][0]
    assert result["status"] == "applied"
    assert result["entity"]["id"] == "exp-client-1"
    assert result["version"] == 1
    assert result["seq"] is not None
    assert body["cursor"] == result["seq"]

    pulled = pull(client, 0, [group.id])
    assert pulled.status_code == 200, pulled.text
    assert pulled.json()["has_more"] is False
    change = pulled.json()["changes"][0]
    assert change["entity_type"] == "expense"
    assert change["op_type"] == "create"
    assert change["snapshot"]["title"] == "Dinner"
    assert change["snapshot"]["paid_for"][0]["participant_id"].startswith("par_")

    bootstrap = client.get("/api/sync/bootstrap", params={"group_id": group.id})
    assert bootstrap.status_code == 200, bootstrap.text
    snapshot = bootstrap.json()
    assert snapshot["group"]["id"] == group.id
    assert {participant["name"] for participant in snapshot["participants"]} == {
        "Alice",
        "Bob",
    }
    assert [expense["id"] for expense in snapshot["expenses"]] == ["exp-client-1"]
    assert len(snapshot["categories"]) == 44
    assert snapshot["cursor"] >= result["seq"]


def test_bootstrap_includes_receipts_and_user_membership(client, session: Session):
    user = make_user(session)
    group, people = make_group(session)
    session.add(
        UserGroup(
            user_id=user.id,
            group_id=group.id,
            is_starred=True,
            is_archived=False,
        )
    )
    expense = make_expense(
        session,
        group=group,
        paid_by=people["Alice"],
        paid_for=[(people["Alice"], 1)],
        amount=500,
    )
    now = datetime.now(UTC)
    receipt = Receipt(
        id="rcp_1",
        group_id=group.id,
        image_url="https://example.com/receipt.jpg",
        status="PARSED",
        total=500,
        expense_id=expense.id,
        created_at=now,
    )
    session.add(receipt)
    session.add(
        ReceiptItem(
            id="ritem_1",
            receipt_id=receipt.id,
            name="Soup",
            amount=500,
            position=0,
            created_at=now,
        )
    )
    session.add(
        ReceiptItemPortion(
            id="rportion_1",
            item_id="ritem_1",
            target=people["Alice"].id,
            participant_id=people["Alice"].id,
            quantity_milli=1000,
            created_at=now,
        )
    )
    session.add(
        ReceiptOptOut(
            id="ropt_1",
            receipt_id=receipt.id,
            participant_id=people["Bob"].id,
            created_at=now,
        )
    )
    session.commit()

    response = client.get(
        "/api/sync/bootstrap",
        params={"group_id": group.id},
        headers=access_headers(user),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["user_group"]["user_id"] == user.id
    assert body["user_group"]["is_starred"] is True
    assert body["receipts"][0]["receipt"]["id"] == "rcp_1"
    assert body["receipts"][0]["items"][0]["name"] == "Soup"
    assert body["receipts"][0]["portions"][0]["target"] == people["Alice"].id
    assert body["receipts"][0]["opt_outs"][0]["participant_id"] == people["Bob"].id


def test_replayed_operation_applies_once(client, session: Session):
    group, people = make_group(session)
    envelope = operation(
        op_id="op-replay",
        group_id=group.id,
        entity_type="expense",
        entity_id="exp-replay",
        payload=expense_payload(people),
    )
    first = push(client, [envelope]).json()["results"][0]
    second = push(client, [envelope]).json()["results"][0]

    assert first == second
    assert first["status"] == "applied"
    session.expire_all()
    assert len(session.exec(select(Expense)).all()) == 1
    assert len(session.exec(select(SyncChange)).all()) == 1


def test_duplicate_create_with_new_operation_is_idempotent(client, session: Session):
    group, people = make_group(session)
    first = operation(
        op_id="op-create-a",
        group_id=group.id,
        entity_type="expense",
        entity_id="exp-dup",
        payload=expense_payload(people),
    )
    second = operation(
        op_id="op-create-b",
        group_id=group.id,
        entity_type="expense",
        entity_id="exp-dup",
        payload=expense_payload(people, title="Different title"),
    )
    assert push(client, [first]).json()["results"][0]["status"] == "applied"
    replay = push(client, [second]).json()["results"][0]

    assert replay["status"] == "applied"
    assert replay["duplicate"] is True
    assert replay["entity"]["id"] == "exp-dup"
    assert replay["entity"]["title"] == "Dinner"
    session.expire_all()
    assert len(session.exec(select(Expense)).all()) == 1
    assert len(session.exec(select(SyncChange)).all()) == 1


def test_participant_crud_tombstone_and_last_writer_wins(client, session: Session):
    group, _ = make_group(session, participants=("Alice",))

    create = operation(
        op_id="op-par-create",
        group_id=group.id,
        entity_type="participant",
        entity_id="par-client",
        payload={"name": "Bob"},
    )
    assert push(client, [create]).json()["results"][0]["status"] == "applied"

    update = operation(
        op_id="op-par-update",
        group_id=group.id,
        entity_type="participant",
        entity_id="par-client",
        op_type="update",
        base_version=1,
        payload={"name": "Robert"},
    )
    stale_update = operation(
        op_id="op-par-update-stale",
        group_id=group.id,
        entity_type="participant",
        entity_id="par-client",
        op_type="update",
        base_version=1,
        payload={"name": "Bobby"},
    )
    assert push(client, [update]).json()["results"][0]["status"] == "applied"
    # Participant names are last-writer-wins even when the client is stale.
    lww = push(client, [stale_update]).json()["results"][0]
    assert lww["status"] == "applied"
    assert lww["entity"]["name"] == "Bobby"
    assert lww["version"] == 3

    delete = operation(
        op_id="op-par-delete",
        group_id=group.id,
        entity_type="participant",
        entity_id="par-client",
        op_type="delete",
        base_version=3,
    )
    assert push(client, [delete]).json()["results"][0]["status"] == "applied"

    listed = client.get(f"/api/groups/{group.id}/participants").json()
    assert "par-client" not in {row["id"] for row in listed}
    after_delete = operation(
        op_id="op-par-update-after-delete",
        group_id=group.id,
        entity_type="participant",
        entity_id="par-client",
        op_type="update",
        base_version=3,
        payload={"name": "Ghost"},
    )
    conflict = push(client, [after_delete]).json()["results"][0]
    assert conflict["status"] == "conflict"
    assert conflict["server_entity"]["deleted_at"] is not None

    changes = pull(client, 0, [group.id]).json()["changes"]
    assert [change["op_type"] for change in changes] == [
        "create",
        "update",
        "update",
        "delete",
    ]
    assert changes[-1]["snapshot"]["deleted_at"] is not None


def test_group_create_requires_tier_and_creates_participants(client, session: Session):
    sync_user = make_user(session, tier=UserTier.SYNC_USERS)
    creator = make_user(session, tier=UserTier.GROUP_CREATORS)
    create = operation(
        op_id="op-group-create-sync-user",
        group_id="grp-offline",
        entity_type="group",
        entity_id="grp-offline",
        payload={
            "name": "Offline trip",
            "currency": "$",
            "currency_code": "USD",
            "participants": [
                {"id": "par-offline-a", "name": "Alice"},
                {"id": "par-offline-b", "name": "Bob"},
            ],
        },
    )
    creator_create = {
        **create,
        "op_id": "op-group-create-creator",
    }

    forbidden = push(client, [create], headers=access_headers(sync_user)).json()["results"][0]
    assert forbidden["status"] == "error"
    assert forbidden["code"] == "forbidden"

    applied = push(client, [creator_create], headers=access_headers(creator)).json()["results"][0]
    assert applied["status"] == "applied"
    assert applied["entity"]["id"] == "grp-offline"
    session.expire_all()
    assert session.get(Group, "grp-offline") is not None
    assert len(session.exec(select(Participant)).all()) == 2
    assert len(session.exec(select(UserGroup)).all()) == 1
    changes = pull(client, 0, ["grp-offline"], limit=10).json()["changes"]
    assert [change["entity_type"] for change in changes] == [
        "group",
        "participant",
        "participant",
    ]


def test_group_update_is_last_writer_wins(client, session: Session):
    group, _ = make_group(session)
    first = operation(
        op_id="op-group-update-1",
        group_id=group.id,
        entity_type="group",
        entity_id=group.id,
        op_type="update",
        base_version=1,
        payload={"name": "Renamed"},
    )
    second = operation(
        op_id="op-group-update-2",
        group_id=group.id,
        entity_type="group",
        entity_id=group.id,
        op_type="update",
        base_version=1,
        payload={"information": "Second writer"},
    )
    assert push(client, [first]).json()["results"][0]["status"] == "applied"
    result = push(client, [second]).json()["results"][0]
    assert result["status"] == "applied"
    assert result["version"] == 3
    assert result["entity"]["name"] == "Renamed"
    assert result["entity"]["information"] == "Second writer"


def test_user_group_is_lww_and_scoped_to_its_user(client, session: Session):
    group, _ = make_group(session)
    first_user = make_user(session)
    second_user = make_user(session)
    create = operation(
        op_id="op-member-create",
        group_id=group.id,
        entity_type="user_group",
        entity_id=group.id,
        payload={"is_starred": True},
    )
    anonymous = push(client, [create]).json()["results"][0]
    assert anonymous["status"] == "error"
    assert anonymous["code"] == "forbidden"

    first = push(
        client,
        [{**create, "op_id": "op-member-create-authenticated"}],
        headers=access_headers(first_user),
    ).json()["results"][0]
    assert first["status"] == "applied"

    own_pull = pull(client, 0, [group.id], headers=access_headers(first_user)).json()
    assert [change["entity_type"] for change in own_pull["changes"]] == ["user_group"]
    assert own_pull["changes"][0]["snapshot"]["is_starred"] is True

    assert pull(client, 0, [group.id]).json()["changes"] == []
    other_pull = pull(client, 0, [group.id], headers=access_headers(second_user)).json()
    assert other_pull["changes"] == []

    update = operation(
        op_id="op-member-update",
        group_id=group.id,
        entity_type="user_group",
        entity_id=group.id,
        op_type="update",
        base_version=999,
        payload={"is_archived": True},
    )
    updated = push(client, [update], headers=access_headers(first_user)).json()["results"][0]
    assert updated["status"] == "applied"
    assert updated["version"] == 2
    assert updated["entity"]["is_archived"] is True

    delete = operation(
        op_id="op-member-delete",
        group_id=group.id,
        entity_type="user_group",
        entity_id=group.id,
        op_type="delete",
        base_version=2,
    )
    deleted = push(client, [delete], headers=access_headers(first_user)).json()["results"][0]
    assert deleted["status"] == "applied"
    session.expire_all()
    assert session.get(UserGroup, (first_user.id, group.id)) is None
    tombstone = pull(
        client, own_pull["cursor"], [group.id], headers=access_headers(first_user)
    ).json()["changes"][-1]
    assert tombstone["entity_type"] == "user_group"
    assert tombstone["snapshot"]["deleted_at"] is not None


def test_claim_groups_merges_without_duplication(session: Session):
    user = make_user(session)
    first, _ = make_group(session, name="First")
    second, _ = make_group(session, name="Second")

    claimed = sync_service.claim_groups(
        session,
        user_id=user.id,
        group_ids=[first.id, second.id, "missing"],
        starred_group_ids=[first.id],
        archived_group_ids=[second.id],
    )
    assert {membership.group_id for membership in claimed} == {first.id, second.id}
    first_membership = session.get(UserGroup, (user.id, first.id))
    assert first_membership is not None and first_membership.is_starred is True
    assert session.get(UserGroup, (user.id, second.id)).is_archived is True

    sync_service.claim_groups(
        session,
        user_id=user.id,
        group_ids=[first.id, second.id],
        starred_group_ids=[first.id],
        archived_group_ids=[second.id],
    )
    rows = session.exec(select(UserGroup).where(UserGroup.user_id == user.id)).all()
    assert len(rows) == 2
    assert len(session.exec(select(SyncChange)).all()) == 2


def test_pagination_and_has_more(client, session: Session):
    group, people = make_group(session)
    operations = [
        operation(
            op_id=f"op-page-{index}",
            group_id=group.id,
            entity_type="expense",
            entity_id=f"exp-page-{index}",
            payload=expense_payload(people, title=f"Expense {index}"),
        )
        for index in range(3)
    ]
    push(client, operations)

    first_page = pull(client, 0, [group.id], limit=2).json()
    assert len(first_page["changes"]) == 2
    assert first_page["has_more"] is True
    assert first_page["cursor"] == first_page["changes"][-1]["seq"]

    second_page = pull(client, first_page["cursor"], [group.id], limit=2).json()
    assert len(second_page["changes"]) == 1
    assert second_page["has_more"] is False
    assert second_page["cursor"] == second_page["changes"][-1]["seq"]


def test_expired_and_future_cursors_require_bootstrap(make_client, session: Session):
    client = make_client(sync_change_retention_days=1)
    group, people = make_group(session)
    result = push(
        client,
        [
            operation(
                op_id="op-old",
                group_id=group.id,
                entity_type="expense",
                entity_id="exp-old",
                payload=expense_payload(people),
            )
        ],
    ).json()["results"][0]
    assert result["status"] == "applied"

    change = session.exec(select(SyncChange).order_by(SyncChange.seq.asc())).first()
    change.changed_at = datetime.now(UTC) - timedelta(days=40)
    session.add(change)
    session.commit()

    expired = pull(client, 0, [group.id])
    assert expired.status_code == 409, expired.text
    assert expired.json()["detail"] == "bootstrap_required"

    future = pull(client, 9999, [group.id])
    assert future.status_code == 409
    assert future.json()["detail"] == "bootstrap_required"

    bootstrap = client.get("/api/sync/bootstrap", params={"group_id": group.id})
    assert bootstrap.status_code == 200
    assert bootstrap.json()["expenses"][0]["id"] == "exp-old"


def test_unknown_entities_fields_and_cross_group_are_rejected(client, session: Session):
    group, people = make_group(session)
    other, other_people = make_group(session, name="Other")
    other_expense = make_expense(
        session,
        group=other,
        paid_by=other_people["Alice"],
        paid_for=[(other_people["Alice"], 1)],
        amount=500,
        expense_id="exp-other",
    )
    assert other_expense.id == "exp-other"

    results = push(
        client,
        [
            operation(
                op_id="op-unknown-entity",
                group_id=group.id,
                entity_type="mystery",
                entity_id="x",
            ),
            operation(
                op_id="op-unknown-field",
                group_id=group.id,
                entity_type="expense",
                entity_id="exp-unknown-field",
                payload={**expense_payload(people), "surprise": True},
            ),
            operation(
                op_id="op-unknown-nested",
                group_id=group.id,
                entity_type="expense",
                entity_id="exp-unknown-nested",
                payload={
                    **expense_payload(people),
                    "paid_for": [{"participant_id": people["Alice"].id, "shares": 1, "extra": 1}],
                },
            ),
            operation(
                op_id="op-cross-group",
                group_id=group.id,
                entity_type="expense",
                entity_id="exp-other",
                op_type="update",
                base_version=1,
                payload={"title": "Stolen"},
            ),
            operation(
                op_id="op-cross-group-participant",
                group_id=group.id,
                entity_type="expense",
                entity_id="exp-cross-participant",
                payload={
                    **expense_payload(people),
                    "paid_by_id": other_people["Alice"].id,
                    "paid_for": [{"participant_id": other_people["Alice"].id, "shares": 1}],
                },
            ),
        ],
    ).json()["results"]

    assert results[0]["status"] == "error" and results[0]["code"] == "unknown_entity"
    assert results[1]["status"] == "error" and results[1]["code"] == "unknown_field"
    assert results[2]["status"] == "error" and results[2]["code"] == "unknown_field"
    assert results[3]["status"] == "error" and results[3]["code"] == "cross_group"
    assert results[4]["status"] == "error"
    assert results[4]["code"] == "validation_error"


def test_one_invalid_operation_does_not_block_valid_work(client, session: Session):
    group, people = make_group(session)
    results = push(
        client,
        [
            operation(
                op_id="op-invalid",
                group_id=group.id,
                entity_type="expense",
                entity_id="exp-invalid",
                payload={**expense_payload(people), "amount": "not-a-number"},
            ),
            operation(
                op_id="op-valid-after-invalid",
                group_id=group.id,
                entity_type="expense",
                entity_id="exp-valid-after-invalid",
                payload=expense_payload(people, title="Valid"),
            ),
        ],
    ).json()["results"]

    assert results[0]["status"] == "error"
    assert results[0]["code"] == "validation_error"
    assert results[1]["status"] == "applied"
    session.expire_all()
    assert session.get(Expense, "exp-valid-after-invalid") is not None
    assert session.get(Expense, "exp-invalid") is None


def test_duplicate_recurring_creates_do_not_duplicate_links(client, session: Session):
    group, people = make_group(session)
    first = operation(
        op_id="op-recurring-a",
        group_id=group.id,
        entity_type="expense",
        entity_id="exp-recurring",
        payload=expense_payload(people, recurrence_rule="MONTHLY"),
    )
    second = operation(
        op_id="op-recurring-b",
        group_id=group.id,
        entity_type="expense",
        entity_id="exp-recurring",
        payload=expense_payload(people, recurrence_rule="MONTHLY"),
    )
    assert push(client, [first]).json()["results"][0]["status"] == "applied"
    assert push(client, [second]).json()["results"][0]["duplicate"] is True

    links = session.exec(select(RecurringExpenseLink)).all()
    assert len(links) == 1
    assert links[0].current_frame_expense_id == "exp-recurring"

    # Materializing the same due frame twice must not create a second frame.
    link = links[0]
    moment = datetime.now(UTC)
    link.next_expense_date = moment - timedelta(days=1)
    session.add(link)
    session.commit()
    assert (
        expenses_service.materialize_due_recurring_expenses(session, group_id=group.id, now=moment)
        == 1
    )
    assert (
        expenses_service.materialize_due_recurring_expenses(session, group_id=group.id, now=moment)
        == 0
    )
    changes = pull(client, 0, [group.id], limit=10).json()["changes"]
    assert [change["op_type"] for change in changes] == ["create", "create"]
    assert changes[-1]["snapshot"]["id"] != "exp-recurring"
    assert (
        changes[-1]["snapshot"]["expense_date"] == (moment - timedelta(days=1)).date().isoformat()
    )
    assert len(session.exec(select(Expense)).all()) == 2


def test_bootstrap_missing_group_returns_404(client):
    response = client.get("/api/sync/bootstrap", params={"group_id": "missing"})
    assert response.status_code == 404


def test_activity_is_written_by_sync_expense_mutations(client, session: Session):
    group, people = make_group(session)
    push(
        client,
        [
            operation(
                op_id="op-activity-create",
                group_id=group.id,
                entity_type="expense",
                entity_id="exp-activity",
                payload=expense_payload(people),
            )
        ],
    )
    update = operation(
        op_id="op-activity-update",
        group_id=group.id,
        entity_type="expense",
        entity_id="exp-activity",
        op_type="update",
        base_version=1,
        payload={"title": "Updated dinner"},
    )
    push(client, [update])
    session.expire_all()
    activities = session.exec(
        select(Activity).where(Activity.group_id == group.id).order_by(Activity.time.asc())
    ).all()
    assert [activity.activity_type for activity in activities] == [
        "CREATE_EXPENSE",
        "UPDATE_EXPENSE",
    ]


def test_expense_date_and_version_envelope(client, session: Session):
    group, people = make_group(session)
    push(
        client,
        [
            operation(
                op_id="op-date",
                group_id=group.id,
                entity_type="expense",
                entity_id="exp-date",
                payload=expense_payload(people, expense_date="2026-02-03"),
            )
        ],
    )
    snapshot = pull(client, 0, [group.id]).json()["changes"][0]["snapshot"]
    assert snapshot["expense_date"] == "2026-02-03"
    assert snapshot["created_at"].endswith("Z")
    assert snapshot["updated_at"].endswith("Z")
    assert snapshot["version"] == 1
    assert snapshot["deleted_at"] is None
    assert snapshot["conversion_rate"] is None

    stored = session.get(Expense, "exp-date")
    assert stored is not None
    assert stored.expense_date.date() == date(2026, 2, 3)
    assert stored.deleted_at is None
