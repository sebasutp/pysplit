"""User table (legacy Prisma ``User``)."""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Field

from app.models.base import SyncColumns, utc_now
from app.models.types import UTCDateTime


class User(SyncColumns, table=True):
    __tablename__ = "users"

    id: str = Field(primary_key=True, max_length=64)
    name: str | None = Field(default=None, nullable=True)
    email: str | None = Field(default=None, nullable=True, unique=True)
    email_verified: datetime | None = Field(
        default=None,
        sa_type=UTCDateTime,
        nullable=True,
    )
    image: str | None = Field(default=None, nullable=True)
    tier: str = Field(default="sync_users", nullable=False, max_length=32)
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_type=UTCDateTime,
        nullable=False,
    )
