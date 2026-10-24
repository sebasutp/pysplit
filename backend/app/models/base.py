"""Shared columns for synchronizable entities.

Stage 2 adds the versioning columns required by the synchronization contract
(plan §2.5) to every row that can travel through the change feed. Business
columns stay in the per-table modules.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel

from app.models.types import UTCDateTime


def utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(UTC)


class SyncColumns(SQLModel):
    """``updated_at`` / ``version`` / ``deleted_at`` for syncable rows."""

    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_type=UTCDateTime,
        nullable=False,
        index=True,
    )
    version: int = Field(default=1, nullable=False)
    deleted_at: datetime | None = Field(default=None, sa_type=UTCDateTime, nullable=True)
