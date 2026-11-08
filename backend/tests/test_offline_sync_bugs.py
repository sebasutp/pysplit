"""Reproduction tests for offline synchronization bugs documented in offline_sync_review.md.

These tests reproduce:
- Bug 3: Server-side mutations outside /api/sync/push never write to SyncChange
  - Test 3a: Applying an attachment split to an expense via attachments_service.apply_attachment_to_expense
    (or POST /api/groups/{id}/attachments/{att_id}/apply) updates the expense version to 2 on the server,
    but does not write a SyncChange row.
  - Test 3b: Direct REST mutations (POST/PATCH/DELETE /api/groups/{id}/expenses) do not emit SyncChange rows.
- Bug 4: materialize_due_recurring_expenses only emits a SyncChange for the new frame and NOT for current,
  leaving current's is_recurring_head flag stale on incremental pull clients.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlmodel import Session

from app.models.expense import Expense
from app.services import expenses as expenses_service
from tests.helpers import access_headers, make_expense, make_group, make_receipt, make_user
from tests.test_sync import expense_payload, operation, pull, push


def test_bug_3a_apply_attachment_split_emits_sync_change(make_client, session: Session):
    """Bug 3a: Applying receipt split to expense updates server version but emits no SyncChange."""
    client = make_client(enable_receipt_ai=True)
    group, people = make_group(session, participants=("Alice", "Bob"))
    expense = make_expense(
        session,
        group=group,
        paid_by=people["Alice"],
        paid_for=[(people["Alice"], 1), (people["Bob"], 1)],
        amount=1000,
        title="Dinner",
    )
    attachment = make_receipt(
        session,
        group=group,
        items=[
            {
                "name": "Pizza",
                "quantity_milli": 1000,
                "amount": 1000,
                "portions": [
                    {"target": "PARTICIPANT", "participant_id": people["Alice"].id, "ratio": 1.0}
                ],
            }
        ],
    )
    # Pull initially to get baseline cursor
    initial_pull = pull(client, 0, [group.id]).json()
    initial_cursor = initial_pull["cursor"]

    # Apply receipt split to expense via REST API
    resp = client.post(
        f"/api/groups/{group.id}/attachments/{attachment.id}/apply",
        json={"expense_id": expense.id},
    )
    assert resp.status_code == 200, resp.text

    # Verify server expense was actually updated to version 2
    session.expire_all()
    server_expense = session.get(Expense, expense.id)
    assert server_expense is not None
    assert server_expense.version == 2

    # Pull changes since initial cursor - incremental sync clients must receive the update
    pulled = pull(client, initial_cursor, [group.id]).json()
    expense_changes = [
        c
        for c in pulled["changes"]
        if c["entity_type"] == "expense" and c["entity_id"] == expense.id
    ]
    assert len(expense_changes) > 0, (
        f"Bug 3a reproduced: No SyncChange was emitted when applying attachment split to expense. "
        f"Server expense is version {server_expense.version}, but sync pull returned 0 changes: {pulled['changes']}"
    )
    assert expense_changes[-1]["version"] == 2


def test_bug_3b_direct_rest_mutations_emit_sync_change(client, session: Session):
    """Bug 3b: Direct REST mutations to expenses do not emit SyncChange rows."""
    group, people = make_group(session, participants=("Alice", "Bob"))
    # Pull initially to get baseline cursor
    initial_pull = pull(client, 0, [group.id]).json()
    initial_cursor = initial_pull["cursor"]

    # Create expense via direct REST API
    resp = client.post(
        f"/api/groups/{group.id}/expenses",
        json={
            "title": "REST Direct Expense",
            "amount": 2500,
            "expense_date": "2026-03-01",
            "paid_by_id": people["Alice"].id,
            "split_mode": "EVENLY",
            "paid_for": [
                {"participant_id": people["Alice"].id, "shares": 1},
                {"participant_id": people["Bob"].id, "shares": 1},
            ],
        },
    )
    assert resp.status_code in (200, 201), resp.text
    created_id = resp.json()["id"]

    # Pull changes since initial cursor - incremental sync clients must receive the created expense
    pulled = pull(client, initial_cursor, [group.id]).json()
    expense_changes = [
        c
        for c in pulled["changes"]
        if c["entity_type"] == "expense" and c["entity_id"] == created_id
    ]
    assert len(expense_changes) > 0, (
        f"Bug 3b reproduced: No SyncChange was emitted for direct REST expense creation. "
        f"Created expense ID {created_id}, but sync pull returned: {pulled['changes']}"
    )


def test_bug_4_recurring_materialization_emits_sync_change_for_previous_frame(
    client, session: Session
):
    """Bug 4: Recurring expense materialization never emits a SyncChange for the previous frame."""
    group, people = make_group(session, participants=("Alice", "Bob"))
    moment = datetime.now(UTC)

    # Create a recurring expense using sync push so it has a known SyncChange baseline
    push_resp = push(
        client,
        [
            operation(
                op_id="op-rec-head",
                group_id=group.id,
                entity_type="expense",
                entity_id="exp-rec-head",
                payload=expense_payload(
                    people,
                    recurrence_rule="MONTHLY",
                    expense_date=(moment - timedelta(days=35)).date().isoformat(),
                ),
            )
        ],
    )
    assert push_resp.status_code == 200, push_resp.text
    initial_cursor = push_resp.json()["cursor"]

    # Materialize due recurring expenses
    count = expenses_service.materialize_due_recurring_expenses(
        session, group_id=group.id, now=moment
    )
    assert count == 1

    # Verify on database level that exp-rec-head is no longer recurring head
    session.expire_all()
    head = session.get(Expense, "exp-rec-head")
    assert head is not None
    assert head.is_recurring_head is False

    # Pull changes since initial_cursor
    pulled = pull(client, initial_cursor, [group.id]).json()
    changes = pulled["changes"]

    # Incremental pull clients MUST receive an update SyncChange for exp-rec-head with is_recurring_head=False
    head_updates = [
        c for c in changes if c["entity_id"] == "exp-rec-head" and c["op_type"] == "update"
    ]
    assert len(head_updates) > 0, (
        f"Bug 4 reproduced: materialize_due_recurring_expenses only emitted SyncChange for the new frame. "
        f"No update SyncChange was emitted for 'exp-rec-head' (is_recurring_head=False). "
        f"Changes received: {[c['entity_id'] + ':' + c['op_type'] for c in changes]}"
    )
    assert head_updates[-1]["snapshot"]["is_recurring_head"] is False


def test_bug_15a_patch_group_participants_emits_sync_changes(client, session: Session):
    """Bug 15a: PATCH /api/groups/{id} with participants must emit SyncChange rows for participants."""
    group, people = make_group(session, participants=("Alice", "Bob", "Carol"))
    initial_cursor = pull(client, 0, [group.id]).json()["cursor"]

    # PATCH group with participants: Alice renamed, Carol omitted (removed), Dave added
    resp = client.patch(
        f"/api/groups/{group.id}",
        json={
            "participants": [
                {"id": people["Alice"].id, "name": "Alice Renamed"},
                {"id": people["Bob"].id, "name": "Bob"},
                {"name": "Dave"},
            ]
        },
    )
    assert resp.status_code == 200, resp.text

    pulled = pull(client, initial_cursor, [group.id]).json()
    changes = pulled["changes"]

    part_changes = [c for c in changes if c["entity_type"] == "participant"]
    assert len(part_changes) > 0, (
        f"Bug 15a reproduced: PATCH /api/groups/{group.id} updated participants in DB "
        f"but emitted 0 participant SyncChange rows. Changes received: {changes}"
    )

    # Check that update for Alice, delete for Carol, and create for Dave exist
    alice_change = next((c for c in part_changes if c["entity_id"] == people["Alice"].id), None)
    carol_change = next((c for c in part_changes if c["entity_id"] == people["Carol"].id), None)
    dave_change = next((c for c in part_changes if c["op_type"] == "create"), None)

    assert alice_change is not None and alice_change["op_type"] == "update"
    assert carol_change is not None and carol_change["op_type"] == "delete"
    assert dave_change is not None


def test_bug_15b_delete_participant_emits_sync_change_with_incremented_version(
    client, session: Session
):
    """Bug 15b: DELETE /api/groups/{id}/participants/{pid} must emit SyncChange with version 2 and deleted_at set."""
    group, people = make_group(session, participants=("Alice", "Bob"))
    initial_cursor = pull(client, 0, [group.id]).json()["cursor"]

    resp = client.delete(f"/api/groups/{group.id}/participants/{people['Bob'].id}")
    assert resp.status_code == 204, resp.text

    pulled = pull(client, initial_cursor, [group.id]).json()
    bob_changes = [
        c
        for c in pulled["changes"]
        if c["entity_type"] == "participant" and c["entity_id"] == people["Bob"].id
    ]
    assert len(bob_changes) > 0, "No SyncChange emitted for participant deletion"
    last_change = bob_changes[-1]
    assert last_change["op_type"] == "delete"
    assert last_change["version"] == 2, (
        f"Bug 15b reproduced: participant delete SyncChange recorded before DB update, "
        f"version is {last_change['version']} instead of 2"
    )
    assert last_change["snapshot"].get("deleted_at") is not None, (
        "Bug 15b reproduced: participant delete SyncChange snapshot has deleted_at=None"
    )


def test_bug_15c_membership_patch_emits_sync_change(client, session: Session):
    """Bug 15c: PATCH /api/groups/{id}/membership must emit a user_group SyncChange."""
    user = make_user(session)
    group, _ = make_group(session)
    headers = access_headers(user)

    initial_cursor = pull(client, 0, [group.id], headers=headers).json()["cursor"]

    resp = client.patch(
        f"/api/groups/{group.id}/membership",
        json={"is_starred": True},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    pulled = pull(client, initial_cursor, [group.id], headers=headers).json()
    user_group_changes = [c for c in pulled["changes"] if c["entity_type"] == "user_group"]
    assert len(user_group_changes) > 0, (
        f"Bug 15c reproduced: PATCH /membership did not emit user_group SyncChange. "
        f"Changes: {pulled['changes']}"
    )
    assert user_group_changes[-1]["snapshot"]["is_starred"] is True
