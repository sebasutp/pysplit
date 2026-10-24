"""Receipt table (legacy Prisma ``Receipt``)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import UniqueConstraint
from sqlmodel import Field

from app.models.base import SyncColumns, utc_now
from app.models.types import UTCDateTime


class Receipt(SyncColumns, table=True):
    __tablename__ = "receipts"
    __table_args__ = (UniqueConstraint("group_id", "image_url", name="uq_receipts_group_image"),)

    id: str = Field(primary_key=True, max_length=64)
    group_id: str = Field(
        foreign_key="groups.id",
        ondelete="CASCADE",
        index=True,
        nullable=False,
        max_length=64,
    )
    image_url: str = Field(nullable=False)
    image_width: int | None = Field(default=None, nullable=True)
    image_height: int | None = Field(default=None, nullable=True)
    status: str = Field(default="PENDING", nullable=False, max_length=32)
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
    expense_id: str | None = Field(
        default=None,
        foreign_key="expenses.id",
        ondelete="SET NULL",
        unique=True,
        nullable=True,
        max_length=64,
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_type=UTCDateTime,
        nullable=False,
    )
