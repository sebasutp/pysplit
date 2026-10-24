"""Statistics business logic."""

from __future__ import annotations

from datetime import date

from sqlmodel import Session

from app.models.group import Group
from app.schemas.stats import (
    CategorySpending,
    DrilldownExpense,
    ExpenseDrilldown,
    ParticipantSpending,
    RecurringPeriod,
    RecurringStats,
    SpendingPeriod,
    SpendingSummary,
    StatsOverview,
    StatsRange,
)
from app.services.errors import NotFoundError
from app.services.expenses import (
    active_recurring_expenses,
    group_expense_snapshot,
    materialize_due_recurring_expenses,
)
from app.services.groups import get_participants
from app.utils.dates import datetime_to_date
from app.utils.totals import (
    calculate_share,
    filter_expenses_by_date_range,
    get_expenses_by_category,
    get_expenses_by_month,
    get_recurring_spending,
    get_spending_by_category,
    get_spending_by_participant,
    get_spending_over_time,
    get_spending_summary,
    get_total_active_user_paid_for,
    get_total_active_user_share,
    get_total_group_spending,
)


def _require_group(session: Session, group_id: str) -> Group:
    group = session.get(Group, group_id)
    if group is None or group.deleted_at is not None:
        raise NotFoundError("group not found")
    return group


def _summary(raw: dict) -> SpendingSummary:
    first_date = raw.get("firstDate")
    last_date = raw.get("lastDate")
    first = date.fromisoformat(first_date) if first_date else None
    last = date.fromisoformat(last_date) if last_date else None
    return SpendingSummary(
        expense_count=int(raw["expenseCount"]),
        total_spending=int(raw["totalSpending"]),
        average_expense=int(raw["averageExpense"]),
        largest_expense=raw.get("largestExpense"),
        first_date=first,
        last_date=last,
        expenseCount=int(raw["expenseCount"]),
        totalSpending=int(raw["totalSpending"]),
        averageExpense=int(raw["averageExpense"]),
        largestExpense=raw.get("largestExpense"),
        firstDate=first,
        lastDate=last,
    )


def _participant_spending(rows: list[dict]) -> list[ParticipantSpending]:
    return [
        ParticipantSpending(
            participant_id=str(row["participantId"]),
            name=str(row["name"]),
            amount=int(row["paid"]),
            paid=int(row["paid"]),
            paid_count=int(row["paidCount"]),
            share=int(row["share"]),
            participantId=str(row["participantId"]),
            paidCount=int(row["paidCount"]),
        )
        for row in rows
    ]


def _category_spending(rows: list[dict]) -> list[CategorySpending]:
    return [
        CategorySpending(
            category_id=int(row["categoryId"]),
            grouping=str(row["grouping"]),
            name=str(row["name"]),
            amount=int(row["total"]),
            total=int(row["total"]),
            categoryId=int(row["categoryId"]),
        )
        for row in rows
    ]


def _recurring_stats(rows: dict) -> RecurringStats:
    by_period = [
        RecurringPeriod(
            period=str(row["period"]),
            count=int(row["count"]),
            total=int(row["total"]),
        )
        for row in rows["byPeriod"]
    ]
    return RecurringStats(
        active_count=int(rows["count"]),
        monthly_amount=int(rows["estimatedMonthly"]),
        yearly_amount=int(rows["estimatedYearly"]),
        count=int(rows["count"]),
        estimated_monthly=int(rows["estimatedMonthly"]),
        estimated_yearly=int(rows["estimatedYearly"]),
        by_period=by_period,
        estimatedMonthly=int(rows["estimatedMonthly"]),
        estimatedYearly=int(rows["estimatedYearly"]),
        byPeriod=by_period,
    )


def stats_overview(
    session: Session,
    group_id: str,
    *,
    participant_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> StatsOverview:
    _require_group(session, group_id)
    materialize_due_recurring_expenses(session, group_id=group_id)
    all_expenses = group_expense_snapshot(session, group_id)
    date_from_text = date_from.isoformat() if date_from else None
    date_to_text = date_to.isoformat() if date_to else None
    expenses = filter_expenses_by_date_range(all_expenses, date_from_text, date_to_text)

    participants = get_participants(session, group_id)
    participant_rows = get_spending_by_participant(
        [{"id": participant.id, "name": participant.name} for participant in participants],
        expenses,
    )
    recurring_rows = active_recurring_expenses(session, group_id)
    recurring_stats = get_recurring_spending(
        [
            {
                "amount": expense.amount,
                "recurrence_rule": expense.recurrence_rule,
                "is_reimbursement": expense.is_reimbursement,
            }
            for expense in recurring_rows
        ]
    )

    total_group = get_total_group_spending(expenses)
    total_paid = (
        get_total_active_user_paid_for(participant_id, expenses)
        if participant_id is not None
        else None
    )
    total_share = (
        get_total_active_user_share(participant_id, expenses)
        if participant_id is not None
        else None
    )
    months = get_spending_over_time(expenses)
    categories = get_spending_by_category(expenses)
    summary = _summary(get_spending_summary(expenses))

    month_rows = [
        SpendingPeriod(
            month=str(row["month"]),
            total=int(row["total"]),
            period=str(row["month"]),
            amount=int(row["total"]),
        )
        for row in months
    ]
    category_rows = _category_spending(categories)
    participant_spendings = _participant_spending(participant_rows)
    recurring = _recurring_stats(recurring_stats)

    return StatsOverview(
        range=StatsRange(from_=date_from, to=date_to),
        total_group_spending=total_group,
        total_active_user_share=total_share,
        total_active_user_paid_for=total_paid,
        summary=summary,
        spending_over_time=month_rows,
        spending_by_participant=participant_spendings,
        spending_by_category=category_rows,
        recurring=recurring,
        totalGroupSpendings=total_group,
        totalParticipantSpendings=total_paid,
        totalParticipantShare=total_share,
        months=month_rows,
        participants=participant_spendings,
        categories=category_rows,
    )


def _drilldown(rows: list[dict]) -> ExpenseDrilldown:
    return ExpenseDrilldown(
        expenses=[
            DrilldownExpense(
                id=str(expense["id"]),
                title=str(expense["title"]),
                amount=int(expense["amount"]),
                expense_date=datetime_to_date(expense["expense_date"]),
                created_at=expense.get("created_at"),
            )
            for expense in rows
        ]
    )


def category_expenses(
    session: Session,
    group_id: str,
    category_id: int,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> ExpenseDrilldown:
    _require_group(session, group_id)
    materialize_due_recurring_expenses(session, group_id=group_id)
    expenses = group_expense_snapshot(session, group_id)
    filtered = filter_expenses_by_date_range(
        expenses,
        date_from.isoformat() if date_from else None,
        date_to.isoformat() if date_to else None,
    )
    return _drilldown(get_expenses_by_category(filtered, category_id))


def month_expenses(
    session: Session,
    group_id: str,
    month: str,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> ExpenseDrilldown:
    _require_group(session, group_id)
    materialize_due_recurring_expenses(session, group_id=group_id)
    expenses = group_expense_snapshot(session, group_id)
    filtered = filter_expenses_by_date_range(
        expenses,
        date_from.isoformat() if date_from else None,
        date_to.isoformat() if date_to else None,
    )
    return _drilldown(get_expenses_by_month(filtered, month))


def active_participant_share(
    session: Session,
    group_id: str,
    participant_id: str,
) -> int:
    """Convenience helper used by tests and the future local-first mirror."""
    _require_group(session, group_id)
    expenses = group_expense_snapshot(session, group_id)
    return sum(calculate_share(participant_id, expense) for expense in expenses)
