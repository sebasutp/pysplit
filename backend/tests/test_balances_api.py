"""Stage 5C tests: balances and suggested reimbursements."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from sqlalchemy import create_engine
from sqlmodel import Session

from app.services.expenses import group_expense_snapshot
from app.utils.balances import (
    get_balances,
    get_public_balances,
    get_suggested_reimbursements,
)
from scripts.legacy_importer import import_database
from tests.helpers import make_expense, make_group

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
LEGACY_FIXTURE = BACKEND / "tests" / "fixtures" / "legacy" / "legacy_fixture.db"
BALANCE_GOLDEN = ROOT / "shared" / "fixtures" / "legacy" / "balances-legacy-fixture.json"


def _expense(expense_id, paid_by, amount, paid_for, split_mode="EVENLY", reimbursement=False):
    return {
        "id": expense_id,
        "amount": amount,
        "paid_by_id": paid_by,
        "paid_for": [
            {"participant_id": participant_id, "shares": shares}
            for participant_id, shares in paid_for
        ],
        "split_mode": split_mode,
        "is_reimbursement": reimbursement,
    }


def test_balance_math():
    expenses = [
        _expense("exp-a", "alice", 1000, [("alice", 1), ("bob", 1)]),
        _expense("exp-b", "bob", 600, [("bob", 1), ("carol", 2)], split_mode="BY_SHARES"),
        _expense("exp-c", "carol", -500, [("alice", 1), ("carol", 1)]),
    ]
    balances = get_balances(expenses)
    assert balances["alice"] == {"paid": 1000, "paidFor": 250, "total": 750}
    assert balances["bob"] == {"paid": 600, "paidFor": 700, "total": -100}
    assert balances["carol"] == {"paid": -500, "paidFor": 150, "total": -650}
    assert sum(values["total"] for values in balances.values()) == 0

    reimbursements = get_suggested_reimbursements(balances)
    assert sum(row["amount"] for row in reimbursements) == 750
    assert all(row["amount"] > 0 for row in reimbursements)

    public = get_public_balances(reimbursements)
    assert sum(values["total"] for values in public.values()) == 0
    assert all(values["total"] != 0 for values in public.values())


def test_balance_math_matches_reference_fixture(tmp_path):
    target = tmp_path / "legacy.db"
    import_database(LEGACY_FIXTURE, target)
    engine = create_engine(f"sqlite:///{target}")
    expected = json.loads(BALANCE_GOLDEN.read_text())["groups"]
    try:
        with Session(engine) as legacy_session:
            for group_id, participants in expected.items():
                balances = get_balances(group_expense_snapshot(legacy_session, group_id))
                assert balances == participants, group_id
    finally:
        engine.dispose()


def test_group_balances(client, session: Session):
    group, people = make_group(session, participants=("Alice", "Bob", "Carol"))
    make_expense(
        session,
        group=group,
        paid_by=people["Alice"],
        paid_for=[(people["Alice"], 1), (people["Bob"], 1)],
        amount=1000,
        expense_date=date(2026, 1, 1),
    )
    make_expense(
        session,
        group=group,
        paid_by=people["Bob"],
        paid_for=[(people["Bob"], 1), (people["Carol"], 2)],
        amount=600,
        split_mode="BY_SHARES",
        expense_date=date(2026, 2, 1),
    )

    expected_balances = get_balances(group_expense_snapshot(session, group.id))
    expected_reimbursements = get_suggested_reimbursements(expected_balances)
    expected_public = get_public_balances(expected_reimbursements)

    response = client.get(f"/api/groups/{group.id}/balances")
    assert response.status_code == 200, response.text
    body = response.json()

    assert {entry["participant_id"]: entry["total"] for entry in body["balances"]} == {
        key: value["total"] for key, value in expected_public.items()
    }
    assert [
        {"from": row["from"], "to": row["to"], "amount": row["amount"]}
        for row in body["reimbursements"]
    ] == expected_reimbursements
    assert sum(entry["total"] for entry in body["balances"]) == 0

    assert client.get("/api/groups/missing/balances").status_code == 404


def test_global_balance(client, session: Session):
    first_group, first_people = make_group(session, name="First")
    second_group, second_people = make_group(session, name="Second")
    make_expense(
        session,
        group=first_group,
        paid_by=first_people["Alice"],
        paid_for=[(first_people["Alice"], 1), (first_people["Bob"], 1)],
        amount=1000,
    )
    make_expense(
        session,
        group=second_group,
        paid_by=second_people["Bob"],
        paid_for=[(second_people["Alice"], 1), (second_people["Bob"], 1)],
        amount=800,
    )

    params = {
        "groups": f"{first_group.id}:{first_people['Alice'].id},"
        f"{second_group.id}:{second_people['Alice'].id},missing:missing"
    }
    response = client.get("/api/balances", params=params)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 2
    assert {item["group_id"]: item["amount"] for item in body["items"]} == {
        first_group.id: 500,
        second_group.id: -400,
    }
    assert body["items"][0]["group_name"] == "First"
    assert body["items"][0]["currency_code"] == "USD"

    assert client.get("/api/balances").json()["items"] == []
    assert client.get("/api/balances", params={"groups": "invalid"}).status_code == 422
