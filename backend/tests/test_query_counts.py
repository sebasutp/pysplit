"""Regression tests for batched serialization query counts."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from sqlalchemy import event
from sqlmodel import Session

from app.services.expenses import list_expenses
from app.services.groups import get_group_details
from tests.helpers import make_expense, make_group

# Generous upper bound: the batched implementation uses a small constant
# number of statements regardless of the number of expenses on the page.
MAX_SERIALIZATION_STATEMENTS = 12


class _StatementCounter:
    def __init__(self) -> None:
        self.count = 0

    def __call__(self, *_args: object, **_kwargs: object) -> None:
        self.count += 1


def _count_statements(engine, action: Callable[[], object]) -> int:
    counter = _StatementCounter()
    event.listen(engine, "before_cursor_execute", counter)
    try:
        action()
    finally:
        event.remove(engine, "before_cursor_execute", counter)
    return counter.count


def _seed_expenses(session: Session):
    group, people = make_group(session)
    for index in range(20):
        make_expense(
            session,
            group=group,
            paid_by=people["Alice"],
            paid_for=[(people["Alice"], 1), (people["Bob"], 1)],
            amount=1000 + index,
            title=f"Expense {index}",
            expense_date=date(2026, 1, 1),
        )
    session.expire_all()
    return group


def test_list_expenses_uses_constant_queries(session: Session, engine):
    group = _seed_expenses(session)

    count = _count_statements(
        engine,
        lambda: list_expenses(session, group.id, limit=50),
    )
    assert count <= MAX_SERIALIZATION_STATEMENTS, count


def test_group_details_uses_constant_queries(session: Session, engine):
    group = _seed_expenses(session)

    count = _count_statements(
        engine,
        lambda: get_group_details(session, group.id),
    )
    assert count <= MAX_SERIALIZATION_STATEMENTS, count
