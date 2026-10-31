"""Applying an attachment receipt split to an expense."""

from __future__ import annotations

from sqlmodel import Session

from app.models.attachment import Attachment
from app.models.expense import Expense
from tests.helpers import make_expense, make_group, make_receipt


def _receipt(session: Session, *, items, opt_outs=()):
    group, people = make_group(session, participants=("Alice", "Bob", "Carol"))
    resolved_items = items(people) if callable(items) else items
    resolved_opt_outs = opt_outs(people) if callable(opt_outs) else opt_outs
    attachment = make_receipt(
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
    return group, people, attachment, expense


def _apply(client, group_id, attachment_id, expense_id, participant_id=None):
    body = {"expense_id": expense_id}
    if participant_id:
        body["participant_id"] = participant_id
    response = client.post(
        f"/api/groups/{group_id}/attachments/{attachment_id}/apply",
        json=body,
    )
    expense = None
    if response.status_code == 200:
        expense = client.get(f"/api/groups/{group_id}/expenses/{expense_id}").json()
    return response, expense


def test_apply_split(make_client, session: Session):
    client = make_client(enable_receipt_ai=True)
    group, people, attachment, expense = _receipt(
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
    response, body = _apply(client, group.id, attachment.id, expense.id)
    assert response.status_code == 200, response.text
    assert body["id"] == expense.id
    assert body["split_mode"] == "BY_AMOUNT"
    assert body["amount"] == response.json()["split"]["items_total"] == 1500
    assert body["notes"] == "keep me"
    assert response.json()["attachment"]["expense_id"] == expense.id
    shares = {row["participant_id"]: row["shares"] for row in body["paid_for"]}
    assert sum(shares.values()) == 1500
    assert shares[people["Alice"].id] == 1168
    assert shares[people["Bob"].id] == 166
    assert shares[people["Carol"].id] == 166


def test_apply_zero_shares_are_filtered(make_client, session: Session):
    client = make_client(enable_receipt_ai=True)
    group, people, attachment, expense = _receipt(
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
    response, body = _apply(client, group.id, attachment.id, expense.id)
    assert response.status_code == 200, response.text
    assert [row["participant_id"] for row in body["paid_for"]] == [people["Alice"].id]
    assert body["paid_for"][0]["shares"] == 1000


def test_apply_invariants_all_opted_out(make_client, session: Session):
    client = make_client(enable_receipt_ai=True)
    group, _people, attachment, expense = _receipt(
        session,
        items=[{"name": "Bread", "quantity_milli": 1000, "amount": 1000}],
        opt_outs=lambda people: (people["Alice"].id, people["Bob"].id, people["Carol"].id),
    )
    response, _body = _apply(client, group.id, attachment.id, expense.id)
    assert response.status_code == 422
    assert "opted out" in response.json()["detail"].lower()


def test_apply_invariants_empty_and_negative(make_client, session: Session):
    client = make_client(enable_receipt_ai=True)
    group, _people, attachment, expense = _receipt(session, items=[])
    empty, _body = _apply(client, group.id, attachment.id, expense.id)
    assert empty.status_code == 422
    assert "no items" in empty.json()["detail"].lower()

    group, _people, attachment, expense = _receipt(
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
    negative, _body = _apply(client, group.id, attachment.id, expense.id)
    assert negative.status_code == 422
    assert "negative" in negative.json()["detail"].lower()


def test_apply_from_button(make_client, session: Session):
    client = make_client(enable_receipt_ai=True)
    group, people, attachment, expense = _receipt(
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
    response, body = _apply(
        client,
        group.id,
        attachment.id,
        expense.id,
        participant_id=people["Bob"].id,
    )
    assert response.status_code == 200, response.text
    assert body["paid_for"][0]["participant_id"] == people["Bob"].id


def test_apply_cross_group_is_rejected(make_client, session: Session):
    client = make_client(enable_receipt_ai=True)
    group, _people, attachment, expense = _receipt(
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
    response, _body = _apply(client, group.id, attachment.id, other_expense.id)
    assert response.status_code == 404
    missing, _body = _apply(client, group.id, "missing", expense.id)
    assert missing.status_code == 404


def test_apply_preserves_other_expense_fields(make_client, session: Session):
    client = make_client(enable_receipt_ai=True)
    group, people = make_group(session, participants=("Alice", "Bob"))
    attachment = make_receipt(
        session,
        group=group,
        items=[{"name": "Coffee", "quantity_milli": 1000, "amount": 500}],
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
    response, body = _apply(client, group.id, attachment.id, expense.id)
    assert response.status_code == 200, response.text
    assert body["title"] == "Dinner"
    assert body["notes"] == "keep me"

    session.expire_all()
    stored = session.get(Expense, expense.id)
    assert stored is not None and stored.amount == 500
    stored_attachment = session.get(Attachment, attachment.id)
    assert stored_attachment is not None and stored_attachment.expense_id == expense.id
