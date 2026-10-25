"""Stage 7 tests: applying a receipt split to an expense."""

from __future__ import annotations

from sqlmodel import Session

from app.models.expense import Expense
from tests.helpers import make_expense, make_group, make_receipt


def _receipt(session: Session, *, items, opt_outs=()):
    group, people = make_group(session, participants=("Alice", "Bob", "Carol"))
    resolved_items = items(people) if callable(items) else items
    resolved_opt_outs = opt_outs(people) if callable(opt_outs) else opt_outs
    receipt = make_receipt(
        session,
        group=group,
        items=resolved_items,
        opt_outs=resolved_opt_outs,
    )
    expense = make_expense(
        session,
        group=group,
        paid_by=people["Alice"],
        paid_for=[(people["Alice"], 1), (people["Bob"], 1)],
        amount=1000,
        title="Dinner",
        notes="keep me",
    )
    return group, people, receipt, expense


def _apply_payload(client, group_id, receipt_id, expense_id, participant_id=None):
    body = {"expense_id": expense_id}
    if participant_id:
        body["participant_id"] = participant_id
    return client.post(
        f"/api/groups/{group_id}/receipts/{receipt_id}/apply",
        json=body,
    )


def test_apply_split(make_client, session: Session):
    client = make_client(enable_receipt_items=True)
    group, people, receipt, expense = _receipt(
        session,
        items=lambda people: [
            {
                "name": "Pizza",
                "quantity_milli": 1000,
                "amount": 1000,
                "portions": [
                    {
                        "target": "PARTICIPANT",
                        "participant_id": people["Alice"].id,
                        "quantity_milli": 1000,
                    }
                ],
            },
            {
                "name": "Tax",
                "quantity_milli": 1000,
                "amount": 100,
                "is_shared": True,
            },
            {"name": "Bread", "quantity_milli": 1000, "amount": 400},
        ],
    )

    response = _apply_payload(client, group.id, receipt.id, expense.id)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["expense"]["id"] == expense.id
    assert body["expense"]["split_mode"] == "BY_AMOUNT"
    assert body["expense"]["amount"] == body["split"]["items_total"] == 1500
    assert body["expense"]["notes"] == "keep me"
    assert body["receipt"]["expense_id"] == expense.id

    shares = {row["participant_id"]: row["shares"] for row in body["expense"]["paid_for"]}
    assert sum(shares.values()) == 1500
    assert all(value > 0 for value in shares.values())
    assert shares[people["Alice"].id] == 1168
    assert shares[people["Bob"].id] == 166
    assert shares[people["Carol"].id] == 166


def test_apply_zero_shares_are_filtered(make_client, session: Session):
    client = make_client(enable_receipt_items=True)
    group, people, receipt, expense = _receipt(
        session,
        items=lambda people: [
            {
                "name": "Solo",
                "quantity_milli": 1000,
                "amount": 1000,
                "portions": [
                    {
                        "target": "PARTICIPANT",
                        "participant_id": people["Alice"].id,
                        "quantity_milli": 1000,
                    }
                ],
            }
        ],
    )
    response = _apply_payload(client, group.id, receipt.id, expense.id)
    assert response.status_code == 200, response.text
    paid_for = response.json()["expense"]["paid_for"]
    assert [row["participant_id"] for row in paid_for] == [people["Alice"].id]
    assert paid_for[0]["shares"] == 1000


def test_apply_invariants_all_opted_out(make_client, session: Session):
    client = make_client(enable_receipt_items=True)
    group, _people, receipt, expense = _receipt(
        session,
        items=[{"name": "Bread", "quantity_milli": 1000, "amount": 1000}],
        opt_outs=lambda people: (
            people["Alice"].id,
            people["Bob"].id,
            people["Carol"].id,
        ),
    )
    response = _apply_payload(client, group.id, receipt.id, expense.id)
    assert response.status_code == 422
    assert "opted out" in response.json()["detail"].lower()


def test_apply_invariants_empty_and_negative(make_client, session: Session):
    client = make_client(enable_receipt_items=True)
    group, _people, receipt, expense = _receipt(session, items=[])
    empty = _apply_payload(client, group.id, receipt.id, expense.id)
    assert empty.status_code == 422
    assert "no items" in empty.json()["detail"].lower()

    group, _people, receipt, expense = _receipt(
        session,
        items=lambda people: [
            {
                "name": "Pizza",
                "quantity_milli": 1000,
                "amount": 1000,
                "portions": [
                    {
                        "target": "PARTICIPANT",
                        "participant_id": people["Alice"].id,
                        "quantity_milli": 1000,
                    }
                ],
            },
            {
                "name": "Adjustment",
                "quantity_milli": 1000,
                "amount": -2000,
                "is_shared": True,
                "is_adjustment": True,
            },
        ],
    )
    negative = _apply_payload(client, group.id, receipt.id, expense.id)
    assert negative.status_code == 422
    assert "negative" in negative.json()["detail"].lower()


def test_apply_from_button(make_client, session: Session):
    """The create-expense screen's apply action uses the same endpoint."""
    client = make_client(enable_receipt_items=True)
    group, people, receipt, expense = _receipt(
        session,
        items=lambda people: [
            {
                "name": "Coffee",
                "quantity_milli": 1000,
                "amount": 500,
                "portions": [
                    {
                        "target": "PARTICIPANT",
                        "participant_id": people["Bob"].id,
                        "quantity_milli": 1000,
                    }
                ],
            }
        ],
    )
    response = _apply_payload(
        client,
        group.id,
        receipt.id,
        expense.id,
        participant_id=people["Bob"].id,
    )
    assert response.status_code == 200, response.text
    assert response.json()["expense"]["paid_for"][0]["participant_id"] == people["Bob"].id


def test_apply_cross_group_is_rejected(make_client, session: Session):
    client = make_client(enable_receipt_items=True)
    group, _people, receipt, expense = _receipt(
        session,
        items=[{"name": "Coffee", "quantity_milli": 1000, "amount": 500}],
    )
    other_group, other_people = make_group(session, name="Other")
    other_expense = make_expense(
        session,
        group=other_group,
        paid_by=other_people["Alice"],
        paid_for=[(other_people["Alice"], 1)],
        amount=1000,
    )
    response = _apply_payload(client, group.id, receipt.id, other_expense.id)
    assert response.status_code == 404

    # Applying to a missing receipt or expense is also NOT_FOUND.
    assert _apply_payload(client, group.id, "missing", expense.id).status_code == 404


def test_apply_restores_expense_documents(make_client, session: Session):
    client = make_client(enable_receipt_items=True)
    group, people = make_group(session, participants=("Alice", "Bob"))
    receipt = make_receipt(
        session,
        group=group,
        items=[{"name": "Coffee", "quantity_milli": 1000, "amount": 500}],
    )
    make_expense(
        session,
        group=group,
        paid_by=people["Alice"],
        paid_for=[(people["Alice"], 1), (people["Bob"], 1)],
        amount=1000,
        title="Dinner",
    )
    # Documents are attached through the normal expense update path.
    document = client.post(
        f"/api/groups/{group.id}/expenses",
        json={
            "expense_date": "2026-09-03",
            "title": "Existing",
            "category_id": 1,
            "amount": 1000,
            "paid_by_id": people["Alice"].id,
            "split_mode": "EVENLY",
            "paid_for": [
                {"participant_id": people["Alice"].id},
                {"participant_id": people["Bob"].id},
            ],
        },
    )
    assert document.status_code == 201
    existing_id = document.json()["id"]
    patched = client.patch(
        f"/api/groups/{group.id}/expenses/{existing_id}",
        json={
            "documents": [
                {
                    "id": "doc-apply",
                    "url": "https://example.com/receipt.jpg",
                    "width": 10,
                    "height": 20,
                }
            ]
        },
    )
    assert patched.status_code == 200, patched.text

    response = _apply_payload(client, group.id, receipt.id, existing_id)
    assert response.status_code == 200, response.text
    assert [doc["id"] for doc in response.json()["expense"]["documents"]] == ["doc-apply"]

    session.expire_all()
    stored = session.get(Expense, existing_id)
    assert stored is not None
    assert stored.amount == 500
