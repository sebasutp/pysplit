"""User-group membership table (legacy Prisma ``UserGroup``)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Index
from sqlmodel import Field

from app.models.base import SyncColumns, utc_now
from app.models.types import UTCDateTime


class UserGroup(SyncColumns, table=True):
    __tablename__ = "user_groups"
    __table_args__ = (Index("ix_user_groups_user_starred", "user_id", "is_starred"),)

    user_id: str = Field(
        primary_key=True,
        foreign_key="users.id",
        ondelete="CASCADE",
        index=True,
        max_length=64,
    )
    group_id: str = Field(
        primary_key=True,
        foreign_key="groups.id",
        ondelete="CASCADE",
        index=True,
        max_length=64,
    )
    is_starred: bool = Field(default=False, nullable=False)
    is_archived: bool = Field(default=False, nullable=False)
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_type=UTCDateTime,
        nullable=False,
    )
