"""Spending statistics and totals.

Pure mirror of ``spliit/src/lib/totals.ts``. Reimbursements are excluded from
spending statistics but included in balances, as in the reference.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from typing import Any

from app.utils.shares import get_expense_shares, get_participant_share

RECURRENCE_PERIODS = ("DAILY", "WEEKLY", "MONTHLY")


def _js_round(value: float) -> int:
    """JavaScript ``Math.round`` semantics (half rounds toward +infinity)."""
    return math.floor(value + 0.5)


PERIOD_FACTORS: dict[str, dict[str, float]] = {
    "DAILY": {"perMonth": 365.25 / 12, "perYear": 365.25},
    "WEEKLY": {"perMonth": 365.25 / 12 / 7, "perYear": 365.25 / 7},
    "MONTHLY": {"perMonth": 1.0, "perYear": 12.0},
}


def expense_date_string(expense: Mapping[str, Any]) -> str:
    """Return the UTC date (``YYYY-MM-DD``) of an expense."""
    value = expense.get("expense_date", expense.get("expenseDate"))
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(UTC)
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value)
    return text[:10]


def _paid_by_id(expense: Mapping[str, Any]) -> str:
    value = expense.get("paid_by_id")
    if value is None and isinstance(expense.get("paidBy"), Mapping):
        value = expense["paidBy"].get("id")
    return str(value)


def _category(expense: Mapping[str, Any]) -> Mapping[str, Any]:
    value = expense.get("category")
    return value if isinstance(value, Mapping) else {}


def _participant_id(value: Any) -> str:
    if isinstance(value, Mapping):
        return str(value.get("id"))
    return str(value)


def _paid_for(expense: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = expense.get("paid_for")
    if raw is None:
        raw = expense.get("paidFor") or []
    rows: list[dict[str, Any]] = []
    for item in raw:  # type: ignore[union-attr]
        if not isinstance(item, Mapping):
            continue
        participant = item.get("participant_id")
        if participant is None and isinstance(item.get("participant"), Mapping):
            participant = item["participant"].get("id")
        if participant is None:
            continue
        rows.append(
            {
                "participant": {"id": str(participant)},
                "participant_id": str(participant),
                "shares": int(item.get("shares", 1)),
            }
        )
    return rows


def _share_input(expense: Mapping[str, Any]) -> dict[str, Any]:
    value = expense.get("expense_date", expense.get("expenseDate"))
    return {
        "id": expense.get("id"),
        "amount": int(expense["amount"]),
        "split_mode": expense.get("split_mode", expense.get("splitMode", "EVENLY")),
        "paid_for": _paid_for(expense),
        "expense_date": value,
    }


def filter_expenses_by_date_range(
    expenses: Sequence[Mapping[str, Any]],
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[Mapping[str, Any]]:
    """Filter to expenses whose UTC date is in the inclusive range."""
    if not date_from and not date_to:
        return list(expenses)
    result: list[Mapping[str, Any]] = []
    for expense in expenses:
        value = expense_date_string(expense)
        if date_from and value < date_from:
            continue
        if date_to and value > date_to:
            continue
        result.append(expense)
    return result


def get_total_group_spending(expenses: Sequence[Mapping[str, Any]]) -> int:
    return sum(
        int(expense["amount"]) for expense in expenses if not expense.get("is_reimbursement", False)
    )


def get_total_active_user_paid_for(
    active_user_id: str | None,
    expenses: Sequence[Mapping[str, Any]],
) -> int:
    return sum(
        int(expense["amount"])
        for expense in expenses
        if _paid_by_id(expense) == active_user_id and not expense.get("is_reimbursement", False)
    )


def calculate_share(participant_id: str | None, expense: Mapping[str, Any]) -> int:
    if expense.get("is_reimbursement", False):
        return 0
    return get_participant_share(participant_id, _share_input(expense))


def get_total_active_user_share(
    active_user_id: str | None,
    expenses: Sequence[Mapping[str, Any]],
) -> int:
    return sum(calculate_share(active_user_id, expense) for expense in expenses)


def get_spending_by_category(
    expenses: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Aggregate non-reimbursement spending by category, highest first."""
    totals: dict[int, dict[str, Any]] = {}
    for expense in expenses:
        if expense.get("is_reimbursement", False):
            continue
        category = _category(expense)
        category_id = int(category.get("id", expense.get("category_id", 0)) or 0)
        amount = int(expense["amount"])
        existing = totals.get(category_id)
        if existing is None:
            totals[category_id] = {
                "categoryId": category_id,
                "grouping": category.get("grouping") or "Uncategorized",
                "name": category.get("name") or "General",
                "total": amount,
            }
        else:
            existing["total"] += amount

    return sorted(
        (row for row in totals.values() if int(row["total"]) != 0),
        key=lambda row: -int(row["total"]),
    )


def get_expenses_by_category(
    expenses: Sequence[Mapping[str, Any]],
    category_id: int,
) -> list[Mapping[str, Any]]:
    matching = [
        expense
        for expense in expenses
        if not expense.get("is_reimbursement", False)
        and int(_category(expense).get("id", expense.get("category_id", 0)) or 0) == category_id
    ]
    return sorted(matching, key=lambda expense: _date_key(expense), reverse=True)


def get_expenses_by_month(
    expenses: Sequence[Mapping[str, Any]],
    month: str,
) -> list[Mapping[str, Any]]:
    matching = [
        expense
        for expense in expenses
        if not expense.get("is_reimbursement", False) and expense_date_string(expense)[:7] == month
    ]
    return sorted(matching, key=lambda expense: _date_key(expense), reverse=True)


def _date_key(expense: Mapping[str, Any]) -> Any:
    value = expense.get("expense_date", expense.get("expenseDate"))
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    return datetime.fromisoformat(str(value)[:19])


def get_spending_by_participant(
    participants: Sequence[Mapping[str, Any]],
    expenses: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    totals: dict[str, dict[str, Any]] = {
        str(participant["id"]): {"paid": 0, "paidCount": 0, "share": 0}
        for participant in participants
    }

    for expense in expenses:
        if expense.get("is_reimbursement", False):
            continue
        payer = totals.get(_paid_by_id(expense))
        if payer is not None:
            payer["paid"] += int(expense["amount"])
            payer["paidCount"] += 1
        for participant_id, share in get_expense_shares(_share_input(expense)).items():
            entry = totals.get(participant_id)
            if entry is not None:
                entry["share"] += share

    rows = [
        {
            "participantId": str(participant["id"]),
            "name": str(participant.get("name", "")),
            "paid": totals[str(participant["id"])]["paid"],
            "paidCount": totals[str(participant["id"])]["paidCount"],
            "share": totals[str(participant["id"])]["share"],
        }
        for participant in participants
    ]
    return sorted(rows, key=lambda row: -int(row["paid"]))


def get_spending_over_time(
    expenses: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    totals: dict[str, int] = {}
    for expense in expenses:
        if expense.get("is_reimbursement", False):
            continue
        month = expense_date_string(expense)[:7]
        totals[month] = totals.get(month, 0) + int(expense["amount"])

    if not totals:
        return []

    months = sorted(totals)
    first_year, first_month = (int(part) for part in months[0].split("-"))
    last_year, last_month = (int(part) for part in months[-1].split("-"))

    result: list[dict[str, Any]] = []
    year, month = first_year, first_month
    while year < last_year or (year == last_year and month <= last_month):
        key = f"{year}-{month:02d}"
        result.append({"month": key, "total": totals.get(key, 0)})
        month += 1
        if month > 12:
            month = 1
            year += 1
    return result


def get_spending_summary(expenses: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    relevant = [expense for expense in expenses if not expense.get("is_reimbursement", False)]
    expense_count = len(relevant)
    total_spending = sum(int(expense["amount"]) for expense in relevant)

    largest: dict[str, Any] | None = None
    for expense in relevant:
        if largest is None or int(expense["amount"]) > int(largest["amount"]):
            largest = {"title": str(expense.get("title", "")), "amount": int(expense["amount"])}

    dates = sorted(expense_date_string(expense) for expense in relevant)
    return {
        "expenseCount": expense_count,
        "totalSpending": total_spending,
        "averageExpense": _js_round(total_spending / expense_count) if expense_count else 0,
        "largestExpense": largest,
        "firstDate": dates[0] if dates else None,
        "lastDate": dates[-1] if dates else None,
    }


def get_recurring_spending(expenses: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_period: list[dict[str, Any]] = []
    for period in RECURRENCE_PERIODS:
        matching = [
            expense
            for expense in expenses
            if not expense.get("is_reimbursement", False)
            and expense.get("recurrence_rule", expense.get("recurrenceRule")) == period
        ]
        by_period.append(
            {
                "period": period,
                "count": len(matching),
                "total": sum(int(expense["amount"]) for expense in matching),
            }
        )

    def estimate(factor: str) -> int:
        return _js_round(
            sum(row["total"] * PERIOD_FACTORS[str(row["period"])][factor] for row in by_period)
        )

    return {
        "count": sum(int(row["count"]) for row in by_period),
        "byPeriod": [row for row in by_period if int(row["count"]) > 0],
        "estimatedMonthly": estimate("perMonth"),
        "estimatedYearly": estimate("perYear"),
    }


def as_stat_expense(expense: Mapping[str, Any]) -> dict[str, Any]:
    """Return the flat expense shape used by the stats helpers."""
    return {
        **_share_input(expense),
        "title": str(expense.get("title", "")),
        "is_reimbursement": bool(expense.get("is_reimbursement", False)),
        "category": dict(_category(expense)),
        "category_id": int(expense.get("category_id", _category(expense).get("id", 0)) or 0),
        "paid_by_id": _paid_by_id(expense),
        "recurrence_rule": expense.get("recurrence_rule", expense.get("recurrenceRule", "NONE")),
    }
