"""Export queries and response payloads."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlmodel import Session, select

from app.formats.exports import (
    content_disposition,
    csv_body,
    csv_filename,
    json_body,
    json_filename,
)
from app.models.activity import Activity
from app.models.participant import Participant
from app.schemas.common import iso_z
from app.services.common import require_group
from app.services.expenses import group_expense_snapshot
from app.utils.dates import datetime_to_date
from app.utils.totals import filter_expenses_by_date_range


@dataclass(frozen=True)
class ExportFile:
    body: bytes
    media_type: str
    filename: str
    disposition: str


def _participants(session: Session, group_id: str) -> list[Participant]:
    return list(session.exec(select(Participant).where(Participant.group_id == group_id)).all())


def _filtered_expenses(
    session: Session,
    group_id: str,
    date_from: date | None,
    date_to: date | None,
) -> list[dict]:
    expenses = group_expense_snapshot(session, group_id)
    filtered = filter_expenses_by_date_range(
        expenses,
        date_from.isoformat() if date_from else None,
        date_to.isoformat() if date_to else None,
    )
    return sorted(
        filtered,
        key=lambda expense: (expense["expense_date"], expense["created_at"], expense["id"]),
    )


def csv_export(
    session: Session,
    group_id: str,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    today: date | None = None,
) -> ExportFile:
    group = require_group(session, group_id)
    participants = _participants(session, group_id)
    expenses = _filtered_expenses(session, group_id, date_from, date_to)
    payload = {
        "id": group.id,
        "name": group.name,
        "information": group.information,
        "currency": group.currency,
        "currency_code": group.currency_code,
        "participants": [
            {"id": participant.id, "name": participant.name} for participant in participants
        ],
    }
    body = csv_body(payload, expenses)
    filename = csv_filename(group.name, (today or datetime_to_date(_now())).isoformat())
    return ExportFile(
        body=body.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        filename=filename,
        disposition=content_disposition(filename),
    )


def _now():
    return datetime.now(UTC)


def _json_expense(expense: dict) -> dict:
    category = expense.get("category")
    return {
        "id": expense["id"],
        "created_at": iso_z(expense["created_at"]),
        "expense_date": datetime_to_date(expense["expense_date"]).isoformat(),
        "title": expense["title"],
        "category": (
            {"grouping": category.get("grouping"), "name": category.get("name")}
            if category
            else None
        ),
        "amount": int(expense["amount"]),
        "original_amount": expense.get("original_amount"),
        "original_currency": expense.get("original_currency"),
        "conversion_rate": expense.get("conversion_rate"),
        "paid_by_id": expense["paid_by_id"],
        "paid_for": [
            {"participant_id": row["participant_id"], "shares": int(row["shares"])}
            for row in expense.get("paid_for", [])
        ],
        "is_reimbursement": bool(expense.get("is_reimbursement")),
        "split_mode": expense.get("split_mode"),
        "recurrence_rule": expense.get("recurrence_rule"),
        "notes": expense.get("notes"),
    }


def json_export(
    session: Session,
    group_id: str,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    today: date | None = None,
) -> ExportFile:
    group = require_group(session, group_id)
    participants = _participants(session, group_id)
    expenses = _filtered_expenses(session, group_id, date_from, date_to)
    activities = session.exec(
        select(Activity)
        .where(Activity.group_id == group_id)
        .order_by(Activity.time.asc(), Activity.id.asc())
    ).all()

    payload = {
        "id": group.id,
        "name": group.name,
        "information": group.information,
        "currency": group.currency,
        "currency_code": group.currency_code,
        "expenses": [_json_expense(expense) for expense in expenses],
        "participants": [
            {"id": participant.id, "name": participant.name} for participant in participants
        ],
        "activities": [
            {
                "id": activity.id,
                "time": iso_z(activity.time),
                "activity_type": activity.activity_type,
                "participant_id": activity.participant_id,
                "expense_id": activity.expense_id,
                "data": activity.data,
            }
            for activity in activities
        ],
    }
    filename = json_filename((today or datetime_to_date(_now())).isoformat())
    return ExportFile(
        body=json_body(payload).encode("utf-8"),
        media_type="application/json",
        filename=filename,
        disposition=content_disposition(filename),
    )
