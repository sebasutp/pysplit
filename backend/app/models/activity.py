"""Activity table (legacy Prisma ``Activity``).

The reference intentionally has no foreign key from an activity to an expense
or participant, so deleted expenses leave orphan activities behind. That is
preserved here.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Index
from sqlmodel import Field

from app.models.base import SyncColumns, utc_now
from app.models.types import UTCDateTime


class Activity(SyncColumns, table=True):
    __tablename__ = "activities"
    __table_args__ = (Index("ix_activities_group_time", "group_id", "time"),)

    id: str = Field(primary_key=True, max_length=64)
    group_id: str = Field(
        foreign_key="groups.id",
        ondelete="CASCADE",
        index=True,
        nullable=False,
        max_length=64,
    )
    time: datetime = Field(
        default_factory=utc_now,
        sa_type=UTCDateTime,
        nullable=False,
    )
    activity_type: str = Field(nullable=False, max_length=64)
    participant_id: str | None = Field(default=None, nullable=True, max_length=64)
    expense_id: str | None = Field(default=None, nullable=True, max_length=64)
    data: str | None = Field(default=None, nullable=True)
