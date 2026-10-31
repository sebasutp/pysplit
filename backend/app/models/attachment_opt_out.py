"""Participant opt-out from an attachment's unassigned pool."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import UniqueConstraint
from sqlmodel import Field

from app.models.base import SyncColumns, utc_now
from app.models.types import UTCDateTime


class AttachmentOptOut(SyncColumns, table=True):
    __tablename__ = "attachment_opt_outs"
    __table_args__ = (
        UniqueConstraint(
            "attachment_id",
            "participant_id",
            name="uq_attachment_opt_outs_attachment_participant",
        ),
    )

    id: str = Field(primary_key=True, max_length=64)
    attachment_id: str = Field(
        foreign_key="attachments.id",
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
