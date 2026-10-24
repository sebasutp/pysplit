"""Receipt opt-out table (legacy Prisma ``ReceiptOptOut``)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import UniqueConstraint
from sqlmodel import Field

from app.models.base import SyncColumns, utc_now
from app.models.types import UTCDateTime


class ReceiptOptOut(SyncColumns, table=True):
    __tablename__ = "receipt_opt_outs"
    __table_args__ = (
        UniqueConstraint(
            "receipt_id",
            "participant_id",
            name="uq_receipt_opt_outs_receipt_participant",
        ),
    )

    id: str = Field(primary_key=True, max_length=64)
    receipt_id: str = Field(
        foreign_key="receipts.id",
        ondelete="CASCADE",
        index=True,
        nullable=False,
        max_length=64,
    )
    participant_id: str = Field(
        foreign_key="participants.id",
        ondelete="CASCADE",
        index=True,
        nullable=False,
        max_length=64,
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_type=UTCDateTime,
        nullable=False,
    )
