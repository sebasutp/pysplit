"""Recurring expense link table (legacy Prisma ``RecurringExpenseLink``)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Index
from sqlmodel import Field

from app.models.base import SyncColumns
from app.models.types import UTCDateTime


class RecurringExpenseLink(SyncColumns, table=True):
    __tablename__ = "recurring_expense_links"
    __table_args__ = (
        Index(
            "ix_recurring_links_group_next",
            "group_id",
            "next_expense_created_at",
            "next_expense_date",
        ),
    )

    id: str = Field(primary_key=True, max_length=64)
    # The reference indexes but does not constrain groupId. Keeping it
    # unconstrained matches rows that may survive a group deletion.
    group_id: str = Field(index=True, nullable=False, max_length=64)
    current_frame_expense_id: str = Field(
        foreign_key="expenses.id",
        ondelete="CASCADE",
        unique=True,
        nullable=False,
        max_length=64,
    )
    next_expense_created_at: datetime | None = Field(
        default=None,
        sa_type=UTCDateTime,
        nullable=True,
    )
    next_expense_date: datetime = Field(sa_type=UTCDateTime, nullable=False)
