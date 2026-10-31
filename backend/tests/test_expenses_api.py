"""Stage 5B tests: expenses, split modes, attachments and updates."""

from __future__ import annotations

from datetime import date

import pytest
from sqlmodel import Session, select

from app.models.activity import Activity
from app.models.attachment import Attachment
from app.models.expense import Expense
from app.models.recurring_expense_link import RecurringExpenseLink
from tests.helpers import make_expense, make_group


def _payload(
    people,
    *,
    amount: int = 1000,
    split_mode: str = "EVENLY",
    paid_for=None,
    **overrides,
):
    body = {
        "expense_date": "2026-09-03",
        "title": "Dinner",
        "category_id": 1,
        "amount": amount,
        "paid_by_id": people["Alice"].id,
        "split_mode": split_mode,
        "paid_for": paid_for
        or [{"participant_id": people["Alice"].id}, {"participant_id": people["Bob"].id}],
    }
    body.update(overrides)
    return body


def test_list_expenses(client, session: Session):
    group, people = make_group(session)
    make_expense(
        session,
        group=group,
        paid_by=people["Alice"],
        paid_for=[(people["Alice"], 1)],
        amount=1000,
        title="Older",
        expense_date=date(2026, 1, 1),
    )
    make_expense(
        session,
        group=group,
        paid_by=people["Alice"],
        paid_for=[(people["Alice"], 1)],
        amount=2000,
        title="Newest",
        expense_date=date(2026, 3, 1),
    )
    make_expense(
        session,
        group=group,
        paid_by=people["Alice"],
        paid_for=[(people["Alice"], 1)],
        amount=3000,
        title="Middle",
        expense_date=date(2026, 2, 1),
    )

    response = client.get(f"/api/groups/{group.id}/expenses")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 3
    assert [item["title"] for item in body["items"]] == ["Newest", "Middle", "Older"]

    page = client.get(
        f"/api/groups/{group.id}/expenses",
        params={"limit": 1, "offset": 1},
    ).json()
    assert page["total"] == 3
    assert [item["title"] for item in page["items"]] == ["Middle"]

    cursor_page = client.get(
        f"/api/groups/{group.id}/expenses",
        params={"limit": 1, "cursor": 2},
    ).json()
    assert [item["title"] for item in cursor_page["items"]] == ["Older"]

    filtered = client.get(
        f"/api/groups/{group.id}/expenses",
        params={"q": "old"},
    ).json()
    assert [item["title"] for item in filtered["items"]] == ["Older"]

    ranged = client.get(
        f"/api/groups/{group.id}/expenses",
        params={"from": "2026-02-01", "to": "2026-02-28"},
    ).json()
    assert [item["title"] for item in ranged["items"]] == ["Middle"]

    assert client.get("/api/groups/missing/expenses").status_code == 404


def test_create_by_amount(client, session: Session):
    group, people = make_group(session)
    payload = _payload(
        people,
        amount=1001,
        split_mode="BY_AMOUNT",
        paid_for=[
            {"participant_id": people["Alice"].id, "amount": 500},
            {"participant_id": people["Bob"].id, "amount": 501},
        ],
        original_amount=1000,
        original_currency="EUR",
        conversion_rate="1.0010",
        notes="Team dinner",
    )
    response = client.post(f"/api/groups/{group.id}/expenses", json=payload)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["amount"] == 1001
    assert body["split_mode"] == "BY_AMOUNT"
    assert body["conversion_rate"] == "1.0010"
    assert body["expense_date"] == "2026-09-03"
    assert {row["participant_id"]: row["shares"] for row in body["paid_for"]} == {
        people["Alice"].id: 500,
        people["Bob"].id: 501,
    }
    assert body["attachments"] == []
    assert body["category"]["id"] == 1

    activity = session.exec(select(Activity).where(Activity.expense_id == body["id"])).one()
    assert activity.activity_type == "CREATE_EXPENSE"
    assert activity.data == "Dinner"

    fetched = client.get(f"/api/groups/{group.id}/expenses/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == body["id"]


def test_create_split_modes(client, session: Session):
    group, people = make_group(session, participants=("Alice", "Bob", "Carol"))

    evenly = client.post(
        f"/api/groups/{group.id}/expenses",
        json=_payload(
            people,
            amount=1000,
            split_mode="EVENLY",
            paid_for=[
                {"participant_id": people["Alice"].id, "shares": 99},
                {"participant_id": people["Bob"].id},
            ],
        ),
    )
    assert evenly.status_code == 201
    assert {row["shares"] for row in evenly.json()["paid_for"]} == {1}

    by_shares = client.post(
        f"/api/groups/{group.id}/expenses",
        json=_payload(
            people,
            amount=1000,
            split_mode="BY_SHARES",
            paid_for=[
                {"participant_id": people["Alice"].id, "shares": 2},
                {"participant_id": people["Bob"].id, "shares": 3},
            ],
        ),
    )
    assert by_shares.status_code == 201
    assert {row["participant_id"]: row["shares"] for row in by_shares.json()["paid_for"]} == {
        people["Alice"].id: 2,
        people["Bob"].id: 3,
    }

    by_percentage = client.post(
        f"/api/groups/{group.id}/expenses",
        json=_payload(
            people,
            amount=1000,
            split_mode="BY_PERCENTAGE",
            paid_for=[
                {"participant_id": people["Alice"].id, "percentage": "33.33"},
                {"participant_id": people["Bob"].id, "percentage": "66.67"},
            ],
        ),
    )
    assert by_percentage.status_code == 201
    assert {row["shares"] for row in by_percentage.json()["paid_for"]} == {3333, 6667}

    integer_percent = client.post(
        f"/api/groups/{group.id}/expenses",
        json=_payload(
            people,
            amount=1000,
            split_mode="BY_PERCENTAGE",
            paid_for=[
                {"participant_id": people["Alice"].id, "shares": 25},
                {"participant_id": people["Bob"].id, "shares": 75},
            ],
        ),
    )
    assert integer_percent.status_code == 201
    assert {row["shares"] for row in integer_percent.json()["paid_for"]} == {2500, 7500}

    comma_percent = client.post(
        f"/api/groups/{group.id}/expenses",
        json=_payload(
            people,
            amount=1000,
            split_mode="BY_PERCENTAGE",
            paid_for=[
                {"participant_id": people["Alice"].id, "shares": "33,33"},
                {"participant_id": people["Bob"].id, "shares": "66,67"},
            ],
        ),
    )
    assert comma_percent.status_code == 201
    assert {row["shares"] for row in comma_percent.json()["paid_for"]} == {3333, 6667}

    invalid_percent = client.post(
        f"/api/groups/{group.id}/expenses",
        json=_payload(
            people,
            amount=1000,
            split_mode="BY_PERCENTAGE",
            paid_for=[
                {"participant_id": people["Alice"].id, "percentage": "10"},
                {"participant_id": people["Bob"].id, "percentage": "20"},
            ],
        ),
    )
    assert invalid_percent.status_code == 422


def test_create_validation(client, session: Session):
    group, people = make_group(session)
    other_group, other_people = make_group(session)

    invalid_participant = client.post(
        f"/api/groups/{group.id}/expenses",
        json=_payload(
            people,
            paid_for=[{"participant_id": other_people["Alice"].id}],
        ),
    )
    assert invalid_participant.status_code == 422

    duplicate = client.post(
        f"/api/groups/{group.id}/expenses",
        json=_payload(
            people,
            paid_for=[
                {"participant_id": people["Alice"].id},
                {"participant_id": people["Alice"].id},
            ],
        ),
    )
    assert duplicate.status_code == 422

    zero = client.post(
        f"/api/groups/{group.id}/expenses",
        json=_payload(people, amount=0),
    )
    assert zero.status_code == 422

    invalid_category = client.post(
        f"/api/groups/{group.id}/expenses",
        json=_payload(people, category_id=9999),
    )
    assert invalid_category.status_code == 422

    amount_sum = client.post(
        f"/api/groups/{group.id}/expenses",
        json=_payload(
            people,
            amount=1000,
            split_mode="BY_AMOUNT",
            paid_for=[
                {"participant_id": people["Alice"].id, "amount": 100},
                {"participant_id": people["Bob"].id, "amount": 100},
            ],
        ),
    )
    assert amount_sum.status_code == 422

    empty_optionals = client.post(
        f"/api/groups/{group.id}/expenses",
        json=_payload(people, original_amount="", conversion_rate="", original_currency=""),
    )
    assert empty_optionals.status_code == 201
    assert empty_optionals.json()["original_amount"] is None
    assert empty_optionals.json()["conversion_rate"] is None
    assert empty_optionals.json()["original_currency"] is None

    created = client.post(f"/api/groups/{group.id}/expenses", json=_payload(people, id="exp-1"))
    assert created.status_code == 201
    conflict = client.post(
        f"/api/groups/{other_group.id}/expenses", json=_payload(other_people, id="exp-1")
    )
    assert conflict.status_code == 409


def test_create_is_idempotent_by_id(client, session: Session):
    group, people = make_group(session)
    first = client.post(f"/api/groups/{group.id}/expenses", json=_payload(people, id="fixed-exp"))
    assert first.status_code == 201
    second = client.post(
        f"/api/groups/{group.id}/expenses",
        json=_payload(people, id="fixed-exp", title="Different"),
    )
    assert second.status_code == 201
    assert second.json()["title"] == "Dinner"
    assert second.json()["version"] == first.json()["version"]
    assert len(session.exec(select(Expense).where(Expense.id == "fixed-exp")).all()) == 1


def test_get_expense(client, session: Session):
    group, people = make_group(session)
    expense = make_expense(
        session,
        group=group,
        paid_by=people["Alice"],
        paid_for=[(people["Alice"], 1)],
        amount=500,
    )
    other_group, _ = make_group(session)
    assert client.get(f"/api/groups/{group.id}/expenses/{expense.id}").status_code == 200
    assert client.get(f"/api/groups/{group.id}/expenses/missing").status_code == 404
    assert client.get(f"/api/groups/{other_group.id}/expenses/{expense.id}").status_code == 404


def test_update_expense(client, session: Session):
    group, people = make_group(session)
    created = client.post(
        f"/api/groups/{group.id}/expenses",
        json=_payload(people),
    ).json()

    partial = client.patch(
        f"/api/groups/{group.id}/expenses/{created['id']}",
        json={"title": "Updated title"},
    )
    assert partial.status_code == 200
    assert partial.json()["title"] == "Updated title"
    assert partial.json()["version"] == 2

    replaced = client.patch(
        f"/api/groups/{group.id}/expenses/{created['id']}",
        json={
            "amount": 1200,
            "split_mode": "BY_SHARES",
            "paid_for": [
                {"participant_id": people["Alice"].id, "shares": 1},
                {"participant_id": people["Bob"].id, "shares": 3},
            ],
            "notes": None,
        },
    )
    assert replaced.status_code == 200, replaced.text
    body = replaced.json()
    assert body["amount"] == 1200
    assert body["split_mode"] == "BY_SHARES"
    assert {row["participant_id"]: row["shares"] for row in body["paid_for"]} == {
        people["Alice"].id: 1,
        people["Bob"].id: 3,
    }
    assert body["attachments"] == []
    assert body["version"] == 3

    activities = session.exec(
        select(Activity).where(Activity.expense_id == created["id"]).order_by(Activity.time.asc())
    ).all()
    assert [activity.activity_type for activity in activities] == [
        "CREATE_EXPENSE",
        "UPDATE_EXPENSE",
        "UPDATE_EXPENSE",
    ]

    invalid = client.patch(
        f"/api/groups/{group.id}/expenses/{created['id']}",
        json={"split_mode": "BY_AMOUNT"},
    )
    assert invalid.status_code == 422
    assert (
        client.patch(
            f"/api/groups/{group.id}/expenses/{created['id']}",
            json={"title": None},
        ).status_code
        == 422
    )


def test_update_expense_base_version_optimistic_concurrency(client, session: Session):
    group, people = make_group(session)
    created = client.post(f"/api/groups/{group.id}/expenses", json=_payload(people)).json()
    assert created["version"] == 1

    stale = client.patch(
        f"/api/groups/{group.id}/expenses/{created['id']}",
        json={"title": "Stale title", "base_version": 0},
    )
    assert stale.status_code == 409, stale.text
    session.expire_all()
    unchanged = session.get(Expense, created["id"])
    assert unchanged is not None
    assert unchanged.title == "Dinner"
    assert unchanged.version == 1

    matching = client.patch(
        f"/api/groups/{group.id}/expenses/{created['id']}",
        json={"title": "Fresh title", "baseVersion": 1},
    )
    assert matching.status_code == 200, matching.text
    assert matching.json()["title"] == "Fresh title"
    assert matching.json()["version"] == 2

    now_stale = client.patch(
        f"/api/groups/{group.id}/expenses/{created['id']}",
        json={"title": "Too late", "base_version": 1},
    )
    assert now_stale.status_code == 409
    session.expire_all()
    assert session.get(Expense, created["id"]).title == "Fresh title"

    # Omitting base_version keeps the previous last-writer-wins behaviour.
    omitted = client.patch(
        f"/api/groups/{group.id}/expenses/{created['id']}",
        json={"title": "No version supplied"},
    )
    assert omitted.status_code == 200, omitted.text
    assert omitted.json()["version"] == 3


def test_expense_input_bounds(client, session: Session):
    group, people = make_group(session)
    created = client.post(f"/api/groups/{group.id}/expenses", json=_payload(people)).json()

    long_title = client.post(
        f"/api/groups/{group.id}/expenses",
        json=_payload(people, title="x" * 201),
    )
    assert long_title.status_code == 422

    too_many_paid_for = client.post(
        f"/api/groups/{group.id}/expenses",
        json=_payload(
            people,
            paid_for=[{"participant_id": people["Alice"].id} for _ in range(101)],
        ),
    )
    assert too_many_paid_for.status_code == 422

    absurd_rate = client.post(
        f"/api/groups/{group.id}/expenses",
        json=_payload(people, conversion_rate="1" * 30),
    )
    assert absurd_rate.status_code == 422

    absurd_shares = client.post(
        f"/api/groups/{group.id}/expenses",
        json=_payload(
            people,
            split_mode="BY_SHARES",
            paid_for=[
                {"participant_id": people["Alice"].id, "shares": 1_000_001},
                {"participant_id": people["Bob"].id, "shares": 1},
            ],
        ),
    )
    assert absurd_shares.status_code == 422

    oversized_update = client.patch(
        f"/api/groups/{group.id}/expenses/{created['id']}",
        json={"title": "x" * 201},
    )
    assert oversized_update.status_code == 422

    absurd_update_rate = client.patch(
        f"/api/groups/{group.id}/expenses/{created['id']}",
        json={"conversion_rate": "9" * 30},
    )
    assert absurd_update_rate.status_code == 422


def test_by_amount_amount_change_requires_new_paid_for(client, session: Session):
    group, people = make_group(session)
    created = client.post(
        f"/api/groups/{group.id}/expenses",
        json=_payload(
            people,
            amount=1000,
            split_mode="BY_AMOUNT",
            paid_for=[
                {"participant_id": people["Alice"].id, "amount": 400},
                {"participant_id": people["Bob"].id, "amount": 600},
            ],
        ),
    ).json()

    rejected = client.patch(
        f"/api/groups/{group.id}/expenses/{created['id']}",
        json={"amount": 1200},
    )
    assert rejected.status_code == 422

    accepted = client.patch(
        f"/api/groups/{group.id}/expenses/{created['id']}",
        json={
            "amount": 1200,
            "paid_for": [
                {"participant_id": people["Alice"].id, "amount": 500},
                {"participant_id": people["Bob"].id, "amount": 700},
            ],
        },
    )
    assert accepted.status_code == 200, accepted.text
    assert {row["shares"] for row in accepted.json()["paid_for"]} == {500, 700}


def test_delete_expense(client, session: Session):
    group, people = make_group(session)
    created = client.post(
        f"/api/groups/{group.id}/expenses",
        json=_payload(people, recurrence_rule="MONTHLY"),
    ).json()
    session.add(
        Attachment(
            id="attachment-delete",
            group_id=group.id,
            expense_id=created["id"],
            storage_key="attachments/delete.png",
            url="/api/groups/x/attachments/attachment-delete/file",
            filename="receipt.png",
            content_type="image/png",
            byte_size=1,
            width=1,
            height=1,
        )
    )
    session.commit()

    response = client.delete(f"/api/groups/{group.id}/expenses/{created['id']}")
    assert response.status_code == 204
    assert client.get(f"/api/groups/{group.id}/expenses/{created['id']}").status_code == 404
    assert client.delete(f"/api/groups/{group.id}/expenses/{created['id']}").status_code == 404

    session.expire_all()
    expense = session.get(Expense, created["id"])
    assert expense is not None and expense.deleted_at is not None
    attachment = session.get(Attachment, "attachment-delete")
    assert attachment is not None and attachment.expense_id is None
    assert attachment.deleted_at is not None
    assert (
        session.exec(
            select(RecurringExpenseLink).where(
                RecurringExpenseLink.current_frame_expense_id == created["id"]
            )
        ).first()
        is None
    )
    activity = session.exec(
        select(Activity).where(
            Activity.group_id == group.id,
            Activity.activity_type == "DELETE_EXPENSE",
        )
    ).one()
    assert activity.data == "Dinner"


def test_upload_download_and_delete_attachment(make_client, session: Session, tmp_path):
    client = make_client(upload_dir=str(tmp_path))
    group, people = make_group(session)
    created = client.post(f"/api/groups/{group.id}/expenses", json=_payload(people)).json()

    upload = client.post(
        f"/api/groups/{group.id}/attachments",
        files={"file": ("receipt.png", b"\x89PNG\r\n\x1a\nexample", "image/png")},
        data={"expense_id": created["id"], "width": "640", "height": "480"},
    )
    assert upload.status_code == 201, upload.text
    attachment = upload.json()
    assert attachment["width"] == 640
    assert attachment["height"] == 480
    assert attachment["url"].endswith(f"/attachments/{attachment['id']}/file")
    assert list((tmp_path / "attachments").rglob("*.png"))

    download = client.get(f"/api/groups/{group.id}/attachments/{attachment['id']}/file")
    assert download.status_code == 200
    assert download.content.startswith(b"\x89PNG")
    assert download.headers["content-type"].startswith("image/png")

    deleted = client.delete(f"/api/groups/{group.id}/attachments/{attachment['id']}")
    assert deleted.status_code == 204
    assert client.get(f"/api/groups/{group.id}/attachments/{attachment['id']}").status_code == 404


@pytest.mark.parametrize(
    ("content_type", "payload", "expected"),
    [
        ("text/plain", b"hello", 422),
        ("image/png", b"", 422),
    ],
)
def test_document_upload_rejects_invalid_types_and_empty(
    make_client,
    session: Session,
    tmp_path,
    content_type,
    payload,
    expected,
):
    client = make_client(upload_dir=str(tmp_path))
    group, people = make_group(session)
    created = client.post(f"/api/groups/{group.id}/expenses", json=_payload(people)).json()
    response = client.post(
        f"/api/groups/{group.id}/attachments",
        files={"file": ("x.bin", payload, content_type)},
        data={"expense_id": created["id"]},
    )
    assert response.status_code == expected


def test_document_upload_enforces_size_limit(make_client, session: Session, tmp_path):
    client = make_client(upload_dir=str(tmp_path), max_upload_bytes=3)
    group, people = make_group(session)
    created = client.post(f"/api/groups/{group.id}/expenses", json=_payload(people)).json()
    response = client.post(
        f"/api/groups/{group.id}/attachments",
        files={"file": ("x.png", b"\x89PNG\r\n\x1a\n", "image/png")},
        data={"expense_id": created["id"]},
    )
    assert response.status_code == 413


def test_document_upload_requires_existing_expense(make_client, session: Session, tmp_path):
    client = make_client(upload_dir=str(tmp_path))
    group, _people = make_group(session)
    response = client.post(
        f"/api/groups/{group.id}/attachments",
        files={"file": ("x.png", b"\x89PNG\r\n\x1a\n", "image/png")},
        data={"expense_id": "missing"},
    )
    assert response.status_code == 404
