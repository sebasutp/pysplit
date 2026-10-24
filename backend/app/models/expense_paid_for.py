"""Expense-paid-for join table (legacy Prisma ``ExpensePaidFor``)."""

from __future__ import annotations

from sqlmodel import Field

from app.models.base import SyncColumns


class ExpensePaidFor(SyncColumns, table=True):
    __tablename__ = "expense_paid_for"

    expense_id: str = Field(
        primary_key=True,
        foreign_key="expenses.id",
        ondelete="CASCADE",
        max_length=64,
    )
    participant_id: str = Field(
        primary_key=True,
        foreign_key="participants.id",
        ondelete="CASCADE",
        index=True,
        max_length=64,
    )
    shares: int = Field(default=1, nullable=False)
