"""Expense table (legacy Prisma ``Expense``)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Index
from sqlmodel import Field

from app.models.base import SyncColumns, utc_now
from app.models.types import DecimalString, UTCDateTime


class Expense(SyncColumns, table=True):
    __tablename__ = "expenses"
    __table_args__ = (
        Index("ix_expenses_group_expense_date", "group_id", "expense_date"),
        Index("ix_expenses_group_created_at", "group_id", "created_at"),
        Index("ix_expenses_paid_by", "paid_by_id"),
    )

    id: str = Field(primary_key=True, max_length=64)
    group_id: str = Field(
        foreign_key="groups.id",
        ondelete="CASCADE",
        index=True,
        nullable=False,
        max_length=64,
    )
    expense_date: datetime = Field(
        default_factory=utc_now,
        sa_type=UTCDateTime,
        nullable=False,
    )
    title: str = Field(nullable=False)
    category_id: int = Field(
        default=0,
        foreign_key="categories.id",
        ondelete="RESTRICT",
        index=True,
        nullable=False,
    )
    amount: int = Field(nullable=False)
    original_amount: int | None = Field(default=None, nullable=True)
    original_currency: str | None = Field(default=None, nullable=True, max_length=8)
    conversion_rate: Decimal | None = Field(
        default=None,
        sa_type=DecimalString,
        nullable=True,
    )
    paid_by_id: str = Field(
        foreign_key="participants.id",
        ondelete="CASCADE",
        nullable=False,
    )
    is_reimbursement: bool = Field(default=False, nullable=False)
    split_mode: str = Field(default="EVENLY", nullable=False, max_length=32)
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_type=UTCDateTime,
        nullable=False,
    )
    notes: str | None = Field(default=None, nullable=True)
    recurrence_rule: str | None = Field(default="NONE", nullable=True, max_length=32)
    # The reference has a circular one-to-one relation between Expense and
    # RecurringExpenseLink. Keep the scalar column without a foreign key to
    # avoid a cycle; the link table owns the actual constraint.
    recurring_expense_link_id: str | None = Field(
        default=None,
        nullable=True,
        index=True,
        max_length=64,
    )
