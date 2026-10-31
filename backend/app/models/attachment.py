"""Unified expense attachment.

An attachment is any uploaded file for a group/expense: image, PDF, or later
another supported type. Receipt extraction state lives on the same row, so a
receipt is simply an attachment that has been processed by AI.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Index
from sqlmodel import Field

from app.models.base import SyncColumns, utc_now
from app.models.types import UTCDateTime


class Attachment(SyncColumns, table=True):
    __tablename__ = "attachments"
    __table_args__ = (
        Index("ix_attachments_group_expense", "group_id", "expense_id"),
        Index("ix_attachments_expense_status", "expense_id", "receipt_status"),
    )

    id: str = Field(primary_key=True, max_length=64)
    group_id: str = Field(
        foreign_key="groups.id",
        ondelete="CASCADE",
        index=True,
        nullable=False,
        max_length=64,
    )
    expense_id: str | None = Field(
        default=None,
        foreign_key="expenses.id",
        ondelete="CASCADE",
        index=True,
        nullable=True,
        max_length=64,
    )
    storage_key: str = Field(nullable=False)
    url: str = Field(nullable=False)
    filename: str = Field(nullable=False)
    content_type: str = Field(nullable=False, max_length=128)
    byte_size: int = Field(default=0, nullable=False)
    width: int = Field(default=1, nullable=False)
    height: int = Field(default=1, nullable=False)
    thumbnail_url: str | None = Field(default=None, nullable=True)

    # Optional receipt extraction state. Generic attachments leave these NULL.
    receipt_status: str | None = Field(default=None, nullable=True, max_length=32)
    attempts: int = Field(default=0, nullable=False)
    raw_extraction: str | None = Field(default=None, nullable=True)
    provider: str | None = Field(default=None, nullable=True, max_length=64)
    model: str | None = Field(default=None, nullable=True, max_length=128)
    merchant: str | None = Field(default=None, nullable=True)
    receipt_date: datetime | None = Field(
        default=None,
        sa_type=UTCDateTime,
        nullable=True,
    )
    currency_code: str | None = Field(default=None, nullable=True, max_length=8)
    total: int | None = Field(default=None, nullable=True)
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_type=UTCDateTime,
        nullable=False,
    )
