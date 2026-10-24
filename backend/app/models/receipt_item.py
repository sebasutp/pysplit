"""Receipt item table (legacy Prisma ``ReceiptItem``)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Index
from sqlmodel import Field

from app.models.base import SyncColumns, utc_now
from app.models.types import UTCDateTime


class ReceiptItem(SyncColumns, table=True):
    __tablename__ = "receipt_items"
    __table_args__ = (Index("ix_receipt_items_receipt_position", "receipt_id", "position"),)

    id: str = Field(primary_key=True, max_length=64)
    receipt_id: str = Field(
        foreign_key="receipts.id",
        ondelete="CASCADE",
        index=True,
        nullable=False,
        max_length=64,
    )
    name: str = Field(nullable=False)
    quantity_milli: int = Field(default=1000, nullable=False)
    unit_price: int | None = Field(default=None, nullable=True)
    amount: int = Field(nullable=False)
    is_shared: bool = Field(default=False, nullable=False)
    is_adjustment: bool = Field(default=False, nullable=False)
    position: int = Field(default=0, nullable=False)
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_type=UTCDateTime,
        nullable=False,
    )
