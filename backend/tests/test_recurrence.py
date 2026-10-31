"""Stage 5B tests: recurring expense materialization and semantics."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlmodel import Session, select

from app.models.attachment import Attachment
from app.models.expense import Expense
from app.models.expense_paid_for import ExpensePaidFor
from app.models.recurring_expense_link import RecurringExpenseLink
from app.services.expenses import (
    MAX_RECURRENCE_FRAMES_PER_REQUEST,
    list_expenses,
    materialize_due_recurring_expenses,
)
from app.utils.recurrence import calculate_next_date
from tests.helpers import make_expense, make_group


def _payload(people, **overrides):
    body = {
        "expense_date": "2026-01-31",
        "title": "Rent",
        "category_id": 1,
        "amount": 10000,
        "paid_by_id": people["Alice"].id,
        "split_mode": "EVENLY",
        "recurrence_rule": "MONTHLY",
        "paid_for": [
            {"participant_id": people["Alice"].id},
            {"participant_id": people["Bob"].id},
        ],
    }
    body.update(overrides)
    return body


def test_calculate_next_date_daily_weekly_monthly_clamp():
    moment = datetime(2026, 1, 31, 10, 30, tzinfo=UTC)
    assert calculate_next_date("DAILY", moment) == datetime(2026, 2, 1, 10, 30, tzinfo=UTC)
    assert calculate_next_date("WEEKLY", moment) == datetime(2026, 2, 7, 10, 30, tzinfo=UTC)
    february = calculate_next_date("MONTHLY", moment)
    assert february == datetime(2026, 2, 28, 10, 30, tzinfo=UTC)
    march = calculate_next_date("MONTHLY", february)
    assert march == datetime(2026, 3, 28, 10, 30, tzinfo=UTC)
    december = calculate_next_date("MONTHLY", datetime(2026, 12, 31, tzinfo=UTC))
    assert december == datetime(2027, 1, 31, tzinfo=UTC)
    assert calculate_next_date("NONE", moment) == moment


def test_create_monthly_recurring_expense_sets_next_link(client, session: Session):
    group, people = make_group(session)
    response = client.post(f"/api/groups/{group.id}/expenses", json=_payload(people))
    assert response.status_code == 201, response.text
    expense_id = response.json()["id"]
    link = session.exec(
        select(RecurringExpenseLink).where(
            RecurringExpenseLink.current_frame_expense_id == expense_id
        )
    ).one()
    assert link.next_expense_date == datetime(2026, 2, 28, tzinfo=UTC)
    assert link.next_expense_created_at is None
    expense = session.get(Expense, expense_id)
    assert expense is not None and expense.recurring_expense_link_id == link.id


def test_materializes_due_frames_once_and_copies_relations(session: Session):
    group, people = make_group(session)
    expense = make_expense(
        session,
        group=group,
        paid_by=people["Alice"],
        paid_for=[(people["Alice"], 1), (people["Bob"], 1)],
        amount=10000,
        title="Subscription",
        expense_date=date(2026, 1, 31),
        category_id=1,
        recurrence_rule="MONTHLY",
    )
    link = RecurringExpenseLink(
        id="link-original",
        group_id=group.id,
        current_frame_expense_id=expense.id,
        next_expense_date=datetime(2026, 2, 28, tzinfo=UTC),
        next_expense_created_at=None,
    )
    session.add(link)
    session.add(
        Attachment(
            id="attachment-recurring",
            group_id=group.id,
            expense_id=expense.id,
            storage_key="attachments/recurring.jpg",
            url="https://example.com/receipt.jpg",
            filename="receipt.jpg",
            content_type="image/jpeg",
            byte_size=1,
            width=10,
            height=20,
        )
    )
    expense.recurring_expense_link_id = link.id
    session.add(expense)
    session.commit()

    created = materialize_due_recurring_expenses(
        session,
        group_id=group.id,
        now=datetime(2026, 4, 1, 12, 0, tzinfo=UTC),
    )
    assert created == 2

    session.expire_all()
    frames = session.exec(
        select(Expense).where(Expense.group_id == group.id).order_by(Expense.expense_date.asc())
    ).all()
    assert [frame.expense_date.date() for frame in frames] == [
        date(2026, 1, 31),
        date(2026, 2, 28),
        date(2026, 3, 28),
    ]
    assert all(frame.amount == 10000 for frame in frames)
    assert all(frame.recurrence_rule == "MONTHLY" for frame in frames)

    for frame in frames[1:]:
        assert (
            len(
                session.exec(
                    select(ExpensePaidFor).where(ExpensePaidFor.expense_id == frame.id)
                ).all()
            )
            == 2
        )

    # Attachments move to the newest frame with the expense.
    attachment = session.get(Attachment, "attachment-recurring")
    assert attachment is not None and attachment.expense_id == frames[-1].id

    links = session.exec(
        select(RecurringExpenseLink).order_by(RecurringExpenseLink.next_expense_date.asc())
    ).all()
    assert len(links) == 3
    assert links[0].next_expense_created_at is not None
    assert links[1].next_expense_created_at is not None
    assert links[-1].next_expense_created_at is None
    assert links[-1].next_expense_date == datetime(2026, 4, 28, tzinfo=UTC)

    # Re-running materialization is a no-op.
    assert (
        materialize_due_recurring_expenses(
            session,
            group_id=group.id,
            now=datetime(2026, 4, 1, 12, 0, tzinfo=UTC),
        )
        == 0
    )


def test_materialization_is_capped_per_call_and_makes_progress(session: Session):
    group, people = make_group(session)
    moment = datetime.now(UTC)
    total_due = MAX_RECURRENCE_FRAMES_PER_REQUEST + 51
    first_frame = (moment - timedelta(days=total_due - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    expense = make_expense(
        session,
        group=group,
        paid_by=people["Alice"],
        paid_for=[(people["Alice"], 1), (people["Bob"], 1)],
        amount=10000,
        title="Daily",
        expense_date=(first_frame - timedelta(days=1)).date(),
        category_id=1,
        recurrence_rule="DAILY",
    )
    link = RecurringExpenseLink(
        id="link-daily",
        group_id=group.id,
        current_frame_expense_id=expense.id,
        next_expense_date=first_frame,
        next_expense_created_at=None,
    )
    expense.recurring_expense_link_id = link.id
    session.add(link)
    session.add(expense)
    session.commit()

    first = materialize_due_recurring_expenses(session, group_id=group.id, now=moment)
    assert first == MAX_RECURRENCE_FRAMES_PER_REQUEST

    session.expire_all()
    pending = session.exec(
        select(RecurringExpenseLink).where(RecurringExpenseLink.next_expense_created_at.is_(None))
    ).one()
    assert pending.next_expense_date < moment

    second = materialize_due_recurring_expenses(session, group_id=group.id, now=moment)
    assert second == total_due - MAX_RECURRENCE_FRAMES_PER_REQUEST
    assert second < MAX_RECURRENCE_FRAMES_PER_REQUEST

    assert materialize_due_recurring_expenses(session, group_id=group.id, now=moment) == 0

    session.expire_all()
    listed = list_expenses(session, group.id, limit=200)
    assert listed.total == total_due + 1
    assert len(listed.items) == total_due + 1
    assert all(len(item.paid_for) == 2 for item in listed.items)
    assert sum(item.amount for item in listed.items) == (total_due + 1) * 10000
    heads = [item for item in listed.items if item.is_recurring_head]
    assert len(heads) == 1
    assert heads[0].expense_date == max(item.expense_date for item in listed.items)


def test_update_recurrence_rule_creates_updates_and_deletes_link(client, session: Session):
    group, people = make_group(session)
    created = client.post(
        f"/api/groups/{group.id}/expenses",
        json=_payload(people, recurrence_rule="NONE"),
    ).json()

    monthly = client.patch(
        f"/api/groups/{group.id}/expenses/{created['id']}",
        json={"recurrence_rule": "MONTHLY"},
    )
    assert monthly.status_code == 200, monthly.text
    link = session.exec(
        select(RecurringExpenseLink).where(
            RecurringExpenseLink.current_frame_expense_id == created["id"]
        )
    ).one()
    assert link.next_expense_date == datetime(2026, 2, 28, tzinfo=UTC)

    weekly = client.patch(
        f"/api/groups/{group.id}/expenses/{created['id']}",
        json={"recurrence_rule": "WEEKLY"},
    )
    assert weekly.status_code == 200
    session.expire_all()
    link = session.exec(
        select(RecurringExpenseLink).where(
            RecurringExpenseLink.current_frame_expense_id == created["id"]
        )
    ).one()
    # Rule changes use the existing frame date, matching the reference.
    assert link.next_expense_date == datetime(2026, 2, 7, tzinfo=UTC)

    unchanged = client.patch(
        f"/api/groups/{group.id}/expenses/{created['id']}",
        json={"title": "Still weekly"},
    )
    assert unchanged.status_code == 200
    session.expire_all()
    link = session.exec(
        select(RecurringExpenseLink).where(
            RecurringExpenseLink.current_frame_expense_id == created["id"]
        )
    ).one()
    assert link.next_expense_date == datetime(2026, 2, 7, tzinfo=UTC)

    none = client.patch(
        f"/api/groups/{group.id}/expenses/{created['id']}",
        json={"recurrence_rule": "NONE"},
    )
    assert none.status_code == 200
    assert (
        session.exec(
            select(RecurringExpenseLink).where(
                RecurringExpenseLink.current_frame_expense_id == created["id"]
            )
        ).first()
        is None
    )


def test_rule_change_after_materialization_conflicts(client, session: Session):
    group, people = make_group(session)
    created = client.post(f"/api/groups/{group.id}/expenses", json=_payload(people)).json()
    link = session.exec(
        select(RecurringExpenseLink).where(
            RecurringExpenseLink.current_frame_expense_id == created["id"]
        )
    ).one()
    link.next_expense_created_at = datetime(2026, 2, 1, tzinfo=UTC)
    session.add(link)
    session.commit()

    response = client.patch(
        f"/api/groups/{group.id}/expenses/{created['id']}",
        json={"recurrence_rule": "WEEKLY"},
    )
    assert response.status_code == 409
