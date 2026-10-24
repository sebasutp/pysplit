"""Expense document table (legacy Prisma ``ExpenseDocument``).

``expense_id`` is nullable because the reference deliberately allows orphan
documents: deleting an expense sets the link to NULL instead of deleting the
uploaded file row.
"""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Field

from app.models.base import SyncColumns, utc_now
from app.models.types import UTCDateTime


class ExpenseDocument(SyncColumns, table=True):
    __tablename__ = "expense_documents"

    id: str = Field(primary_key=True, max_length=64)
    url: str = Field(nullable=False)
    width: int = Field(nullable=False)
    height: int = Field(nullable=False)
    expense_id: str | None = Field(
        default=None,
        foreign_key="expenses.id",
        ondelete="SET NULL",
        index=True,
        nullable=True,
        max_length=64,
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_type=UTCDateTime,
        nullable=False,
    )
