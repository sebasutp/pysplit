"""Group table (legacy Prisma ``Group``)."""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Field

from app.models.base import SyncColumns, utc_now
from app.models.types import UTCDateTime


class Group(SyncColumns, table=True):
    __tablename__ = "groups"

    id: str = Field(primary_key=True, max_length=64)
    name: str = Field(nullable=False)
    information: str | None = Field(default=None, nullable=True)
    currency: str = Field(default="$", nullable=False, max_length=16)
    currency_code: str | None = Field(default=None, nullable=True, max_length=8)
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_type=UTCDateTime,
        nullable=False,
    )
