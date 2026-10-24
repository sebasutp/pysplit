"""Balance endpoints' business logic."""

from __future__ import annotations

from sqlmodel import Session

from app.models.group import Group
from app.models.participant import Participant
from app.schemas.balances import (
    BalanceEntry,
    GroupBalances,
    ReimbursementRead,
    UserBalanceList,
    UserBalanceRead,
)
from app.services.errors import NotFoundError
from app.services.expenses import group_expense_snapshot, materialize_due_recurring_expenses
from app.utils.balances import (
    get_balances,
    get_public_balances,
    get_suggested_reimbursements,
)


def get_group_balances(session: Session, group_id: str) -> GroupBalances:
    group = session.get(Group, group_id)
    if group is None or group.deleted_at is not None:
        raise NotFoundError("group not found")
    materialize_due_recurring_expenses(session, group_id=group_id)
    expenses = group_expense_snapshot(session, group_id)
    balances = get_balances(expenses)
    reimbursements = get_suggested_reimbursements(balances)
    public = get_public_balances(reimbursements)

    return GroupBalances(
        balances=[
            BalanceEntry(
                participant_id=participant_id,
                total=int(values["total"]),
                paid=int(values["paid"]),
                paid_for=int(values["paidFor"]),
            )
            for participant_id, values in sorted(public.items())
        ],
        reimbursements=[
            ReimbursementRead(from_=str(row["from"]), to=str(row["to"]), amount=int(row["amount"]))
            for row in reimbursements
        ],
    )


def balances_for_user(
    session: Session,
    entries: list[tuple[str, str]],
) -> UserBalanceList:
    snapshots: dict[str, list[dict]] = {}
    items: list[UserBalanceRead] = []

    for group_id, participant_id in entries:
        group = session.get(Group, group_id)
        if group is None or group.deleted_at is not None:
            continue
        participant = session.get(Participant, participant_id)
        if participant is None or participant.group_id != group_id:
            continue

        if group_id not in snapshots:
            materialize_due_recurring_expenses(session, group_id=group_id)
            snapshots[group_id] = group_expense_snapshot(session, group_id)
        balances = get_balances(snapshots[group_id])
        amount = int(balances.get(participant_id, {}).get("total", 0))
        items.append(
            UserBalanceRead(
                group_id=group.id,
                group_name=group.name,
                currency=group.currency,
                currency_code=group.currency_code,
                participant_id=participant.id,
                participant_name=participant.name,
                amount=amount,
            )
        )

    return UserBalanceList(
        items=items,
        total=len(items),
        limit=max(1, len(items)),
        offset=0,
    )
