"""Group balance and reimbursement math.

Pure mirror of ``spliit/src/lib/balances.ts``. Amounts are integer minor units;
positive totals mean the participant is owed money.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from functools import cmp_to_key
from typing import Any

from app.utils.shares import get_expense_shares


def _paid_by_id(expense: Mapping[str, Any]) -> str:
    value = expense.get("paid_by_id")
    if value is None and isinstance(expense.get("paidBy"), Mapping):
        value = expense["paidBy"].get("id")
    return str(value)


def get_balances(expenses: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    """Aggregate what each participant paid and what they owe."""
    balances: dict[str, dict[str, int]] = {}

    def entry(participant_id: str) -> dict[str, int]:
        return balances.setdefault(participant_id, {"paid": 0, "paidFor": 0, "total": 0})

    for expense in expenses:
        paid_by = _paid_by_id(expense)
        entry(paid_by)["paid"] += int(expense["amount"])

        for participant_id, divided_amount in get_expense_shares(expense).items():
            entry(participant_id)["paidFor"] += divided_amount

    for values in balances.values():
        values["paid"] = round(values["paid"]) + 0
        values["paidFor"] = round(values["paidFor"]) + 0
        values["total"] = values["paid"] - values["paidFor"]

    return balances


def get_public_balances(
    reimbursements: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, int]]:
    """Derive the public balance display from the suggested reimbursements."""
    balances: dict[str, dict[str, int]] = {}

    def entry(participant_id: str) -> dict[str, int]:
        return balances.setdefault(participant_id, {"paid": 0, "paidFor": 0, "total": 0})

    for reimbursement in reimbursements:
        source = str(reimbursement["from"])
        target = str(reimbursement["to"])
        amount = int(reimbursement["amount"])
        entry(source)["paidFor"] += amount
        entry(source)["total"] -= amount
        entry(target)["paid"] += amount
        entry(target)["total"] += amount

    return balances


def _compare_for_reimbursements(
    first: Mapping[str, Any],
    second: Mapping[str, Any],
) -> int:
    """Stable comparator: positive balances before negative, then by id."""
    first_total = int(first["total"])
    second_total = int(second["total"])
    if first_total > 0 and second_total < 0:
        return -1
    if second_total > 0 and first_total < 0:
        return 1
    return -1 if str(first["participantId"]) < str(second["participantId"]) else 1


def get_suggested_reimbursements(
    balances: Mapping[str, Mapping[str, int]],
) -> list[dict[str, Any]]:
    """Return transfers that settle the group with the reference comparator."""
    entries = [
        {"participantId": participant_id, "total": int(values["total"])}
        for participant_id, values in balances.items()
        if int(values["total"]) != 0
    ]
    entries.sort(key=cmp_to_key(_compare_for_reimbursements))

    reimbursements: list[dict[str, Any]] = []
    while len(entries) > 1:
        first = entries[0]
        last = entries[-1]
        first_total = int(first["total"])
        last_total = int(last["total"])

        if first_total > -last_total:
            reimbursements.append(
                {
                    "from": last["participantId"],
                    "to": first["participantId"],
                    "amount": -last_total,
                }
            )
            first["total"] = first_total + last_total
            entries.pop()
        else:
            reimbursements.append(
                {
                    "from": last["participantId"],
                    "to": first["participantId"],
                    "amount": first_total,
                }
            )
            last["total"] = first_total + last_total
            entries.pop(0)

    return [row for row in reimbursements if int(row["amount"]) != 0]
