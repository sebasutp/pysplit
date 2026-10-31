"""Portion of an attachment item assigned to a participant or shared."""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Field

from app.models.base import SyncColumns, utc_now
from app.models.types import UTCDateTime


class AttachmentItemPortion(SyncColumns, table=True):
    __tablename__ = "attachment_item_portions"

    id: str = Field(primary_key=True, max_length=64)
    item_id: str = Field(
        foreign_key="attachment_items.id",
        ondelete="CASCADE",
        index=True,
        nullable=False,
        max_length=64,
    )
    # "PARTICIPANT" or "SHARED".
    target: str = Field(nullable=False, max_length=64)
    participant_id: str | None = Field(
        default=None,
        foreign_key="participants.id",
        ondelete="CASCADE",
        index=True,
        nullable=True,
        max_length=64,
    )
    quantity_milli: int = Field(nullable=False)
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_type=UTCDateTime,
        nullable=False,
    )
