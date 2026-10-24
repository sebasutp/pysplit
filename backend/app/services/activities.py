"""Activity feed queries."""

from __future__ import annotations

from sqlalchemy import func
from sqlmodel import Session, select

from app.models.activity import Activity
from app.models.expense import Expense
from app.models.group import Group
from app.schemas.activities import ActivityExpenseRef, ActivityList, ActivityRead
from app.services.errors import NotFoundError
from app.utils.dates import datetime_to_date


def list_activities(
    session: Session,
    group_id: str,
    *,
    cursor: int = 0,
    limit: int = 5,
) -> ActivityList:
    group = session.get(Group, group_id)
    if group is None or group.deleted_at is not None:
        raise NotFoundError("group not found")

    total = int(
        session.exec(
            select(func.count()).select_from(Activity).where(Activity.group_id == group_id)
        ).one()
    )
    rows = list(
        session.exec(
            select(Activity)
            .where(Activity.group_id == group_id)
            .order_by(Activity.time.desc(), Activity.id.desc())
            .offset(cursor)
            .limit(limit + 1)
        ).all()
    )
    has_more = len(rows) > limit
    visible = rows[:limit]

    expense_ids = [row.expense_id for row in visible if row.expense_id is not None]
    expenses: dict[str, Expense] = {}
    if expense_ids:
        expense_rows = session.exec(
            select(Expense).where(
                Expense.id.in_(expense_ids),
                Expense.deleted_at.is_(None),
            )
        ).all()
        expenses = {expense.id: expense for expense in expense_rows}

    items = []
    for activity in visible:
        expense = expenses.get(activity.expense_id) if activity.expense_id else None
        items.append(
            ActivityRead(
                id=activity.id,
                group_id=activity.group_id,
                time=activity.time,
                activity_type=activity.activity_type,
                participant_id=activity.participant_id,
                expense_id=activity.expense_id,
                data=activity.data,
                expense=(
                    ActivityExpenseRef(
                        id=expense.id,
                        title=expense.title,
                        amount=expense.amount,
                        expense_date=datetime_to_date(expense.expense_date),
                    )
                    if expense is not None
                    else None
                ),
            )
        )

    return ActivityList(
        items=items,
        next_cursor=str(cursor + limit),
        has_more=has_more,
        total=total,
        limit=limit,
        offset=cursor,
    )
