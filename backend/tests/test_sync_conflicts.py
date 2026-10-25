"""Stage 6 conflict, replay and two-client convergence tests."""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine, select

from app.models.expense import Expense
from app.models.recurring_expense_link import RecurringExpenseLink
from app.models.sync_change import SyncChange
from app.schemas.sync import SyncOperationIn
from app.services import sync as sync_service
from tests.helpers import make_group
from tests.test_sync import expense_payload, operation, pull, push


def test_stale_update_returns_conflict_then_next_edit_applies(client, session: Session):
    group, people = make_group(session)
    push(
        client,
        [
            operation(
                op_id="op-create",
                group_id=group.id,
                entity_type="expense",
                entity_id="exp-conflict",
                payload=expense_payload(people),
            )
        ],
    )

    stale = operation(
        op_id="op-stale",
        group_id=group.id,
        entity_type="expense",
        entity_id="exp-conflict",
        op_type="update",
        base_version=0,
        payload={"title": "Stale title"},
    )
    conflict = push(client, [stale]).json()["results"][0]
    assert conflict["status"] == "conflict"
    assert conflict["version"] == 1
    assert conflict["server_entity"]["title"] == "Dinner"
    assert "seq" not in conflict or conflict["seq"] is None

    valid = operation(
        op_id="op-valid",
        group_id=group.id,
        entity_type="expense",
        entity_id="exp-conflict",
        op_type="update",
        base_version=1,
        payload={"title": "Fresh title"},
    )
    applied = push(client, [valid]).json()["results"][0]
    assert applied["status"] == "applied"
    assert applied["version"] == 2
    assert applied["entity"]["title"] == "Fresh title"

    # Replaying the stale operation returns the stored conflict, not a new
    # reconciliation against the now newer row.
    assert push(client, [stale]).json()["results"][0] == conflict


def test_delete_tombstone_wins_over_updates(client, session: Session):
    group, people = make_group(session)
    push(
        client,
        [
            operation(
                op_id="op-create",
                group_id=group.id,
                entity_type="expense",
                entity_id="exp-delete-conflict",
                payload=expense_payload(people),
            )
        ],
    )
    delete = operation(
        op_id="op-delete",
        group_id=group.id,
        entity_type="expense",
        entity_id="exp-delete-conflict",
        op_type="delete",
        base_version=1,
    )
    deleted = push(client, [delete]).json()["results"][0]
    assert deleted["status"] == "applied"
    assert deleted["version"] == 2
    assert deleted["entity"]["deleted_at"] is not None

    for version in (1, 2):
        update = operation(
            op_id=f"op-update-after-delete-{version}",
            group_id=group.id,
            entity_type="expense",
            entity_id="exp-delete-conflict",
            op_type="update",
            base_version=version,
            payload={"title": "Resurrected"},
        )
        conflict = push(client, [update]).json()["results"][0]
        assert conflict["status"] == "conflict"
        assert conflict["server_entity"]["deleted_at"] is not None
        assert conflict["server_entity"]["title"] == "Dinner"

    # Replaying the delete is idempotent even with a different operation id.
    replay_with_new_id = operation(
        op_id="op-delete-again",
        group_id=group.id,
        entity_type="expense",
        entity_id="exp-delete-conflict",
        op_type="delete",
        base_version=2,
    )
    replay = push(client, [replay_with_new_id]).json()["results"][0]
    assert replay["status"] == "applied"
    assert replay["duplicate"] is True
    session.expire_all()
    assert session.get(Expense, "exp-delete-conflict").version == 2
    deletes = session.exec(
        select(SyncChange).where(
            SyncChange.entity_id == "exp-delete-conflict",
            SyncChange.op_type == "delete",
        )
    ).all()
    assert len(deletes) == 1


def test_tombstone_is_visible_in_pull_after_the_create_cursor(client, session: Session):
    group, people = make_group(session)
    create = push(
        client,
        [
            operation(
                op_id="op-create",
                group_id=group.id,
                entity_type="expense",
                entity_id="exp-tombstone",
                payload=expense_payload(people),
            )
        ],
    ).json()
    create_cursor = create["cursor"]

    delete = operation(
        op_id="op-delete",
        group_id=group.id,
        entity_type="expense",
        entity_id="exp-tombstone",
        op_type="delete",
        base_version=1,
    )
    push(client, [delete])

    changes = pull(client, create_cursor, [group.id]).json()["changes"]
    assert len(changes) == 1
    assert changes[0]["op_type"] == "delete"
    assert changes[0]["snapshot"]["id"] == "exp-tombstone"
    assert changes[0]["snapshot"]["deleted_at"] is not None
    assert changes[0]["snapshot"]["version"] == 2
    assert client.get(f"/api/groups/{group.id}/expenses/exp-tombstone").status_code == 404


def test_two_clients_converge_and_replay_delete_once(make_client, session: Session):
    client_a = make_client()
    client_b = make_client()
    group, people = make_group(session)

    create = operation(
        op_id="client-a-create",
        group_id=group.id,
        entity_type="expense",
        entity_id="exp-converge",
        payload=expense_payload(people, title="Original"),
    )
    created = push(client_a, [create]).json()["results"][0]
    assert created["status"] == "applied" and created["version"] == 1

    b_pull = pull(client_b, 0, [group.id]).json()
    assert b_pull["changes"][-1]["snapshot"]["version"] == 1
    b_cursor = b_pull["cursor"]

    update_b = operation(
        op_id="client-b-update",
        group_id=group.id,
        entity_type="expense",
        entity_id="exp-converge",
        op_type="update",
        base_version=1,
        payload={"title": "Edited on B"},
    )
    updated_b = push(client_b, [update_b]).json()["results"][0]
    assert updated_b["status"] == "applied" and updated_b["version"] == 2

    stale_a = operation(
        op_id="client-a-stale-update",
        group_id=group.id,
        entity_type="expense",
        entity_id="exp-converge",
        op_type="update",
        base_version=1,
        payload={"amount": 999},
    )
    conflict_a = push(client_a, [stale_a]).json()["results"][0]
    assert conflict_a["status"] == "conflict"
    assert conflict_a["server_entity"]["title"] == "Edited on B"

    a_pull = pull(client_a, created["seq"], [group.id]).json()
    assert a_pull["changes"][-1]["snapshot"]["version"] == 2
    update_a = operation(
        op_id="client-a-merged-update",
        group_id=group.id,
        entity_type="expense",
        entity_id="exp-converge",
        op_type="update",
        base_version=2,
        payload={"title": "Merged on A", "amount": 1500},
    )
    updated_a = push(client_a, [update_a]).json()["results"][0]
    assert updated_a["status"] == "applied" and updated_a["version"] == 3

    b_after_a = pull(client_b, b_cursor, [group.id]).json()
    # B sees A's update (and not its own already-known update twice).
    assert b_after_a["changes"][-1]["snapshot"]["version"] == 3
    b_cursor = b_after_a["cursor"]

    delete_b = operation(
        op_id="client-b-delete",
        group_id=group.id,
        entity_type="expense",
        entity_id="exp-converge",
        op_type="delete",
        base_version=3,
    )
    deleted_b = push(client_b, [delete_b]).json()["results"][0]
    assert deleted_b["status"] == "applied" and deleted_b["version"] == 4

    a_after_delete = pull(client_a, a_pull["cursor"], [group.id]).json()
    assert a_after_delete["changes"][-1]["op_type"] == "delete"
    assert a_after_delete["changes"][-1]["snapshot"]["deleted_at"] is not None

    replay = push(client_b, [delete_b]).json()["results"][0]
    assert replay == deleted_b

    session.expire_all()
    expense = session.get(Expense, "exp-converge")
    assert expense is not None
    assert expense.version == 4
    assert expense.deleted_at is not None
    assert expense.title == "Merged on A"
    assert expense.amount == 1500
    changes = session.exec(select(SyncChange).where(SyncChange.entity_id == "exp-converge")).all()
    assert len(changes) == 4
    assert [change.op_type for change in changes] == [
        "create",
        "update",
        "update",
        "delete",
    ]

    # Both clients reconstruct the same final snapshot.
    final_a = pull(client_a, 0, [group.id]).json()["changes"][-1]["snapshot"]
    final_b = pull(client_b, 0, [group.id]).json()["changes"][-1]["snapshot"]
    assert final_a == final_b
    assert final_a["deleted_at"] is not None


def test_concurrent_creates_do_not_duplicate_recurrence_frames(tmp_path):
    """Two writers racing on the same client ID create one expense and one link."""
    database = tmp_path / "sync-concurrency.db"
    concurrent_engine = create_engine(
        f"sqlite:///{database}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )

    @event.listens_for(concurrent_engine, "connect")
    def _pragmas(dbapi_connection, _record):
        if not isinstance(dbapi_connection, sqlite3.Connection):
            return
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=30000")
        finally:
            cursor.close()

    SQLModel.metadata.create_all(concurrent_engine)
    try:
        with Session(concurrent_engine) as seed:
            group, people = make_group(seed)
            group_id = group.id
            payload = expense_payload(people, recurrence_rule="MONTHLY")

        barrier = Barrier(2)

        def worker(op_id: str):
            with Session(concurrent_engine) as session:
                envelope = SyncOperationIn.model_validate(
                    operation(
                        op_id=op_id,
                        group_id=group_id,
                        entity_type="expense",
                        entity_id="exp-concurrent",
                        payload=payload,
                    )
                )
                barrier.wait()
                return sync_service.push_operations(session, [envelope], user_id=None).results[0]

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(worker, ["op-concurrent-a", "op-concurrent-b"]))

        assert {result.status for result in results} == {"applied"}
        assert any(result.duplicate for result in results)
        with Session(concurrent_engine) as check:
            assert len(check.exec(select(Expense)).all()) == 1
            links = check.exec(select(RecurringExpenseLink)).all()
            assert len(links) == 1
            assert len(check.exec(select(SyncChange)).all()) == 1
    finally:
        concurrent_engine.dispose()
